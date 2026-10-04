"""
ArtifactGeneratorAgent — bridges ComprehensionAgent output to execution-ready artifacts.

Two modes (controlled by self.mode):

  mode="intents"     (step: artifact_generator_intents)
    business_scenarios → LLM → deduplicated intent list
    OUTPUT: application_assets/{project}/test_creation/intents.yaml

  mode="testcases"   (step: artifact_generator_testcases)
    intents + test_data → enriched intents + test cases + test suite
    OUTPUT: application_assets/{project}/test_creation/intents.yaml (enriched)
            application_assets/{project}/test_creation/test_cases.yaml
            application_assets/{project}/test_creation/test_suite.yaml
"""

import os
from typing import Dict, Optional

from agents.base_agent import BaseAgent
from agents.test_creation.artifact_generator.prompt import INTENT_GENERATION_PROMPT, TESTCASE_MAPPING_PROMPT
from agents.test_creation.artifact_generator.skills import SKILLS
from connectors.connector_registry import ConnectorRegistry
from agents.test_creation.artifact_generator.tools import (
    build_test_data_ref_map,
    enrich_with_testdata,
    export_artifacts,
    export_intents_only,
    generate_intents,
    generate_suite,
    generate_test_cases,
    load_test_data,
    validate_artifacts,
    IntentDefinition,
)
from tools.testdata.load_scenarios import load_scenarios
from tools.context import ProjectArtifactContext
from tools.discovery.dom_intents import load_dom_intents
from tools.shared import get_logger

from tools.constants import PROJECTS_BASE as _ASSETS_BASE


class ArtifactGeneratorAgent(BaseAgent):
    """
    mode="intents"   — generate intents from business scenarios
    mode="testcases" — generate test cases from intents + test data
    """

    def __init__(self, mode: str = "intents", provider=None, settings: Optional[dict] = None):
        self.mode = mode
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.artifact_generator")

    def execute(self, request: dict, state: dict) -> Dict:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        connector_mode = request.get("connector_mode")
        llm = self._registry.get_llm(connector_mode)

        test_creation_dir = os.path.join(_ASSETS_BASE, safe, "test_creation")
        comprehension_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")

        self.logger.info(f"--- ArtifactGeneratorAgent [{self.mode}] for project '{project_name}' ---")

        # Check discovery output so we know if comprehension actually succeeded
        discovery_out = (state or {}).get("outputs", {}).get("discovery", {})
        if discovery_out.get("comprehension_status") == "failed":
            err = (
                f"Discovery step reported comprehension_status=failed "
                f"({discovery_out.get('comprehension_error', 'unknown reason')}). "
                f"business_scenarios.json was not produced — fix discovery first."
            )
            self.logger.error(err)
            return {"module": f"artifact_generator_{self.mode}", "status": "failed", "error": err}

        # Load project context once — reads existing artifacts + .md files (capped for LLM safety)
        ctx = ProjectArtifactContext.load(project_name, request.get("project_state", {}))

        if self.mode == "intents":
            return self._run_intents(
                project_name, safe, comprehension_dir, test_creation_dir, llm, ctx,
                module_id=request.get("module_filter"),
            )
        elif self.mode == "testcases":
            return self._run_testcases(project_name, safe, comprehension_dir, test_creation_dir, llm, ctx)
        else:
            raise ValueError(f"Unknown ArtifactGeneratorAgent mode: '{self.mode}'")

    # ------------------------------------------------------------------
    # Pass 1: BS → intents
    # ------------------------------------------------------------------

    def _run_intents(
        self, project_name, safe, comprehension_dir, test_creation_dir, llm, ctx: ProjectArtifactContext,
        module_id: Optional[str] = None,
    ) -> Dict:
        self.logger.info("Loading business scenarios")
        try:
            all_scenarios = load_scenarios(comprehension_dir)
        except FileNotFoundError as exc:
            self.logger.error(str(exc))
            return {"module": "artifact_generator_intents", "status": "failed", "error": str(exc)}

        # ── Incremental: only process scenarios not yet covered by existing intents ──
        if ctx.covered_scenario_ids:
            uncovered = [s for s in all_scenarios if s.scenario_id not in ctx.covered_scenario_ids]
            self.logger.info(
                f"{len(ctx.existing_intents_raw)} existing intent(s) cover "
                f"{len(ctx.covered_scenario_ids)} scenario(s) — "
                f"{len(uncovered)} uncovered scenario(s) to process"
            )
        else:
            uncovered = all_scenarios

        if not uncovered:
            intents_path = os.path.join(test_creation_dir, "intents.yaml")
            self.logger.info("All scenarios already covered — skipping LLM call")
            return {
                "module": "artifact_generator_intents",
                "status": "success",
                "project": project_name,
                "scenarios_processed": 0,
                "intents_generated": 0,
                "skipped": True,
                "reason": "all_scenarios_covered",
                "output": {"intents": intents_path},
            }

        self.logger.info(f"Generating intents for {len(uncovered)} uncovered scenario(s)")
        skill_header = SKILLS["artifact_generator"].header()

        # Build extra context for the LLM (capped — safe for token limits)
        extra_subs = {}
        if ctx.existing_intents_compact:
            extra_subs["existing_intents_summary"] = (
                "\n== Already existing intents (DO NOT regenerate these) ==\n"
                + ctx.existing_intents_compact
                + "\n"
            )
        if ctx.format_guide_scenarios:
            extra_subs["md_context"] = ctx.format_guide_scenarios

        try:
            new_intents = generate_intents(
                uncovered, llm, INTENT_GENERATION_PROMPT, skill_header,
                extra_subs=extra_subs if extra_subs else None,
            )
        except ValueError as exc:
            self.logger.error(f"Intent generation failed: {exc}")
            return {"module": "artifact_generator_intents", "status": "failed", "error": str(exc)}

        self.logger.info(f"Generated {len(new_intents)} new intent(s)")

        # ── Renumber new intents so IDs continue from existing ──
        offset = len(ctx.existing_intents_raw)
        new_intents = [
            intent.model_copy(update={"intent_id": f"INT-{offset + j:03d}"})
            for j, intent in enumerate(new_intents, start=1)
        ]

        # ── Ground new intents with DOM locators ──
        dom_intents = _load_dom_intents(safe, module_id)
        if dom_intents:
            new_intents = _apply_dom_locators(new_intents, dom_intents, self.logger)
            grounded = sum(1 for i in new_intents if i.locator_id)
            self.logger.info(f"Grounded {grounded}/{len(new_intents)} new intent(s) with DOM locators")
        else:
            self.logger.info("No DOM intents from discovery — locators will be assigned at step 5")

        # ── Merge: rebuild existing as IntentDefinition objects + append new ──
        existing_as_models = [IntentDefinition(**d) for d in ctx.existing_intents_raw]
        merged_intents = existing_as_models + new_intents

        path = export_intents_only(merged_intents, test_creation_dir, project_name)
        self.logger.info(
            f"Intents exported to '{path}' "
            f"({len(existing_as_models)} existing + {len(new_intents)} new = {len(merged_intents)} total)"
        )

        return {
            "module": "artifact_generator_intents",
            "status": "success",
            "project": project_name,
            "scenarios_processed": len(uncovered),
            "intents_generated": len(new_intents),
            "intents_total": len(merged_intents),
            "dom_grounded": bool(dom_intents),
            "output": {"intents": path},
        }

    # ------------------------------------------------------------------
    # Pass 2: intents + test data → enriched intents + test cases + suite
    # ------------------------------------------------------------------

    def _run_testcases(self, project_name, safe, comprehension_dir, test_creation_dir, llm, ctx: ProjectArtifactContext) -> Dict:
        import yaml

        intents_path = os.path.join(test_creation_dir, "intents.yaml")
        if not os.path.exists(intents_path):
            msg = f"intents.yaml not found at '{intents_path}'. Run artifact_generator_intents first."
            self.logger.error(msg)
            return {"module": "artifact_generator_testcases", "status": "failed", "error": msg}

        self.logger.info("Loading intents")
        with open(intents_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        intents = [IntentDefinition(**i) for i in raw.get("intents", [])]

        self.logger.info("Loading test data for enrichment")
        project_assets_dir = os.path.join(_ASSETS_BASE, safe)
        test_data_records = load_test_data(project_assets_dir)
        if test_data_records:
            self.logger.info(f"Enriching intents with {len(test_data_records)} TD record(s)")
            intents = enrich_with_testdata(intents, test_data_records)
        else:
            self.logger.info("No test data found — fill intents will have null values")

        td_ref_map = build_test_data_ref_map(test_data_records)

        self.logger.info("Loading business scenarios")
        try:
            scenarios = load_scenarios(comprehension_dir)
        except FileNotFoundError as exc:
            self.logger.error(str(exc))
            return {"module": "artifact_generator_testcases", "status": "failed", "error": str(exc)}

        self.logger.info(f"Generating test cases for {len(scenarios)} scenario(s)")
        skill_header = SKILLS["artifact_generator"].header()

        # Build extra context for the LLM — existing TCs as dedup hint + format guide
        extra_subs = {}
        if ctx.existing_tc_compact:
            extra_subs["existing_tc_summary"] = (
                "\n== Already existing test cases (DO NOT regenerate these) ==\n"
                + ctx.existing_tc_compact
                + "\n"
            )
        md_parts = [p for p in [ctx.format_guide_scenarios, ctx.format_guide_testdata] if p]
        if md_parts:
            extra_subs["md_context"] = "\n\n".join(md_parts)

        try:
            test_cases = generate_test_cases(
                scenarios, intents, llm, TESTCASE_MAPPING_PROMPT, skill_header, td_ref_map,
                extra_subs=extra_subs if extra_subs else None,
            )
        except ValueError as exc:
            self.logger.error(f"Test case generation failed: {exc}")
            return {"module": "artifact_generator_testcases", "status": "failed", "error": str(exc)}

        valid_cases, warnings = validate_artifacts(intents, test_cases)
        for w in warnings:
            self.logger.warning(f"Validation: {w}")

        suite_name = safe
        suite = generate_suite(valid_cases, suite_name, project_name)
        paths = export_artifacts(intents, valid_cases, suite, test_creation_dir)

        self.logger.info(
            f"Exported {len(intents)} intents, {len(valid_cases)} test cases, 1 suite"
        )

        return {
            "module": "artifact_generator_testcases",
            "status": "success",
            "project": project_name,
            "intents_enriched": len(intents),
            "test_cases_generated": len(test_cases),
            "test_cases_valid": len(valid_cases),
            "validation_warnings": warnings,
            "output": paths,
        }


def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"


_ACTION_PREFIXES = ("fill_", "click_", "enter_", "select_", "verify_", "navigate_", "hover_")


def _strip_action_prefix(name: str) -> str:
    for prefix in _ACTION_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _load_dom_intents(safe: str, module_id: Optional[str] = None) -> list:
    """Read comprehension/dom_intents.json (module-scoped when module_id is
    given) if DiscoveryAgent wrote one. Thin re-export of the shared
    loader so existing call sites in this module don't need to change."""
    return load_dom_intents(safe, module_id)


def _apply_dom_locators(intents, dom_intents: list, logger) -> list:
    """
    Match each LLM-generated intent to a DOM intent and copy its locator_id.

    Match strategy (in order):
      1. Exact intent_name match
      2. Normalized (strip action prefix) exact match
      3. DOM name is a substring of LLM name (or vice versa) — first wins
    """
    from tools.artifact_generator.models import IntentDefinition

    # Build lookup tables from DOM intents
    by_exact: dict = {}
    by_norm: dict = {}

    for d in dom_intents:
        dname = d.get("intent_name", "")
        locator = d.get("locator_id") or d.get("selector", "")
        if not locator:
            continue
        by_exact[dname] = locator
        by_norm[_strip_action_prefix(dname)] = locator

    result = []
    for intent in intents:
        if intent.locator_id:
            result.append(intent)
            continue

        iname = intent.intent_name
        inorm = _strip_action_prefix(iname)
        locator = None

        # 1. exact
        locator = by_exact.get(iname)
        # 2. normalized exact
        if not locator:
            locator = by_norm.get(inorm)
        # 3. substring fallback
        if not locator:
            for dname, dloc in by_exact.items():
                dnorm = _strip_action_prefix(dname)
                if dnorm in inorm or inorm in dnorm:
                    locator = dloc
                    break

        if locator:
            result.append(intent.model_copy(update={"locator_id": locator}))
        else:
            result.append(intent)

    return result
