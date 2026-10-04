"""
TestDataAgent — generates 8-10 test variants per business scenario.

Failure routing (via BaseAgent.execute_with_fallback):
    Tier 0 — primary LLM (parallel, _MAX_WORKERS at once)
    Tier 1 — NSHTTPConnector  (_run_ns_fallback)
    Tier 2 — Python deterministic  (_run_py_fallback → fallback_core)
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.test_creation.testdata.prompt import TEST_DATA_GENERATION_PROMPT
from agents.test_creation.testdata.skills import SKILLS
from agents.test_creation.testdata.tools import (
    export_test_data,
    generate_test_data,
    load_scenarios,
    validate_test_data,
    ScenarioTestData,
)
from connectors.connector_registry import ConnectorRegistry
from tools.config.test_generation_config import load_test_generation_config
from tools.context import ProjectArtifactContext
from tools.shared import get_logger
from tools.constants import PROJECTS_BASE as _ASSETS_BASE

_MAX_WORKERS = 4


class TestDataAgent(BaseAgent):
    MODULE_NAME = "testdata"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.testdata")

    # ── Public entry point ────────────────────────────────────────────────────

    def execute(self, request: dict, state: dict) -> Dict:
        """Delegate to execute_with_fallback so failure routing applies."""
        return self.execute_with_fallback(request, state)

    # ── Tier 0 — primary LLM ─────────────────────────────────────────────────

    def _run_primary(self, request: dict, state: dict) -> Dict:
        llm = self.registry.get_llm(request.get("connector_mode"))
        return self._llm_pipeline(request, state, llm=llm)

    # ── Tier 1 — NSHTTPConnector ──────────────────────────────────────────────

    def _run_ns_fallback(self, request: dict, state: dict) -> Dict:
        ns = self.registry.get_ns()
        project_name = request.get("project_name") or request.get("message", "project")
        payload = {"project_name": project_name}
        self._log(f"Routing to NSHTTPConnector — project='{project_name}'")
        result = ns.call("testdata_agent", payload)
        if "module" not in result:
            result["module"] = "testdata"
        if "status" not in result:
            result["status"] = "success"
        return result

    # ── Tier 1b — alternate (lighter) model ───────────────────────────────────

    def _run_with_alt_model(self, model: str, request: dict, state: dict) -> Dict:
        self._log(f"Switching to alt model: {model}")
        try:
            from connectors.llm.claude import ClaudeConnector
            alt_llm = ClaudeConnector(model=model)
        except TypeError:
            # ClaudeConnector doesn't support model kwarg yet — use external connector
            alt_llm = self.registry.get_llm("external")
        return self._llm_pipeline(request, state, llm=alt_llm)

    # ── Tier 2 — Python deterministic fallback ────────────────────────────────

    def _run_py_fallback(self, request: dict, state: dict) -> Dict:
        from agents.common import fallback_core

        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        comprehension_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        output_dir = os.path.join(_ASSETS_BASE, safe, "test_creation", "test_data")

        self._log(f"Python fallback — loading scenarios from '{comprehension_dir}'")

        try:
            scenarios_objs = load_scenarios(comprehension_dir)
        except FileNotFoundError as exc:
            return {
                "module": "testdata",
                "status": "failed",
                "project": project_name,
                "error": str(exc),
                "fallback": True,
            }

        scenarios_raw = [
            {
                "scenario_id": s.scenario_id,
                "title": s.title,
                "scenario_name": getattr(s, "scenario_name", s.title),
                "steps": [
                    st if isinstance(st, dict)
                    else {"description": st} if isinstance(st, str)
                    else st.model_dump()
                    for st in s.steps
                ],
            }
            for s in scenarios_objs
        ]
        fallback_data = fallback_core.fallback_generate_test_data(scenarios_raw)

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "test_data.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fallback_data, f, indent=2, ensure_ascii=False)

        self._log(
            f"Python fallback wrote {len(fallback_data)} dataset(s) (3 variants each) → {out_path}"
        )
        return {
            "module": "testdata",
            "status": "degraded",
            "project": project_name,
            "scenarios_processed": len(scenarios_raw),
            "datasets_generated": len(fallback_data),
            "datasets_valid": len(fallback_data),
            "datasets_total": len(fallback_data),
            "validation_warnings": [
                "Python fallback active — 3 variants only (positive, empty, boundary). "
                "Re-run when LLM is available for full 8-10 variant coverage."
            ],
            "fallback": True,
            "output": {"json": out_path},
        }

    # ── Core LLM pipeline (shared by Tier 0 and Tier 1b) ─────────────────────

    def _llm_pipeline(self, request: dict, state: dict, llm) -> Dict:
        project_name = (
            request.get("project_name") or request.get("message", "project")
        )
        self._log(f"Starting LLM pipeline — project='{project_name}'")

        # Fail fast if discovery reported comprehension failure
        discovery_out = (state or {}).get("outputs", {}).get("discovery", {})
        if discovery_out.get("comprehension_status") == "failed":
            from agents.common.failure_classifier import MissingInputError
            raise MissingInputError(
                "Discovery reported comprehension_status=failed — "
                f"{discovery_out.get('comprehension_error', 'unknown reason')}. "
                "business_scenarios.json was not produced."
            )

        safe = _safe_name(project_name)
        comprehension_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        output_dir = os.path.join(_ASSETS_BASE, safe, "test_creation", "test_data")

        self._log(f"Input: {comprehension_dir}")
        self._log(f"Output: {output_dir}")
        self._log(f"Connector: {llm.__class__.__name__}")

        ctx = ProjectArtifactContext.load(project_name, request.get("project_state", {}))
        skill = SKILLS["test_data_generation"]
        skill_header = skill.header()

        # Step 1 — Load scenarios
        try:
            all_scenarios = load_scenarios(comprehension_dir)
        except FileNotFoundError as exc:
            from agents.common.failure_classifier import MissingInputError
            raise MissingInputError(str(exc)) from exc

        # Step 1.5 — Load field name hints from interaction_catalog.json (docs-only, optional)
        catalog_path = os.path.join(comprehension_dir, "interaction_catalog.json")
        scenario_fill_fields = _load_fill_fields_from_catalog(catalog_path)
        if not scenario_fill_fields:
            # Backward-compat: try legacy intents.yaml in test_creation/
            intents_path = os.path.join(_ASSETS_BASE, safe, "test_creation", "intents.yaml")
            scenario_fill_fields = _load_fill_fields_from_intents(intents_path)

        if scenario_fill_fields:
            self._log(f"Field hints loaded for {len(scenario_fill_fields)} scenario(s)")
        else:
            self._log(
                "No interaction_catalog.json or intents.yaml found — "
                "using generic snake_case field_name conventions",
                level="warning",
            )

        # Step 1.6 — Incremental: skip scenarios that already have test data
        if ctx.scenarios_with_test_data:
            uncovered = [
                s for s in all_scenarios if s.scenario_id not in ctx.scenarios_with_test_data
            ]
            self._log(
                f"{len(ctx.scenarios_with_test_data)} scenario(s) already covered — "
                f"{len(uncovered)} to generate"
            )
        else:
            uncovered = all_scenarios

        if not uncovered:
            self._log("All scenarios have test data — skipping LLM call")
            return {
                "module": "testdata",
                "status": "success",
                "project": project_name,
                "scenarios_processed": 0,
                "datasets_generated": 0,
                "datasets_valid": 0,
                "skipped": True,
                "reason": "all_scenarios_have_test_data",
                "validation_warnings": [],
                "output": {
                    "json": os.path.join(output_dir, "test_data.json"),
                    "markdown": os.path.join(output_dir, "test_data.md"),
                },
            }

        format_guide = ctx.format_guide_testdata
        existing_count = len(ctx.existing_test_data_raw)

        self._log(
            f"Generating test data for {len(uncovered)} scenario(s) "
            f"in parallel (workers={_MAX_WORKERS})"
        )

        # Step 2 — Generate (parallel)
        datasets: List = [None] * len(uncovered)

        def _generate(idx_scenario):
            idx, scenario = idx_scenario
            fill_names = scenario_fill_fields.get(scenario.scenario_id, [])
            if fill_names:
                hint = (
                    f"\nIMPORTANT: For field_name values use exactly these names "
                    f"to match the UI elements: {', '.join(fill_names)}\n"
                )
            else:
                hint = (
                    "\nIMPORTANT: Use snake_case field_name values prefixed with the action verb "
                    "(e.g. fill_email, fill_name, fill_phone, select_country, select_role). "
                    "Do NOT use bare names like 'email' or 'name' without a prefix.\n"
                )
            format_hint = (
                f"\n== Existing project test data format (match this style) ==\n{format_guide}\n"
                if format_guide else ""
            )
            gen_config = load_test_generation_config(safe, module_id=scenario.module_id)
            return idx, generate_test_data(
                scenario=scenario,
                llm_connector=llm,
                prompt_template=TEST_DATA_GENERATION_PROMPT,
                skill_header=skill_header,
                testdata_index=existing_count + idx,
                fill_fields_hint=hint,
                existing_format_guide=format_hint,
                max_negative_cases=gen_config["max_negative_cases"],
                max_boundary_cases=gen_config["max_boundary_cases"],
                max_data_iterations=gen_config["max_data_iterations"],
            )

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_generate, (idx, scenario)): scenario
                for idx, scenario in enumerate(uncovered, start=1)
            }
            for future in as_completed(futures):
                scenario = futures[future]
                try:
                    idx, dataset = future.result()
                    datasets[idx - 1] = dataset
                    self._log(
                        f"--- {scenario.scenario_id} done: "
                        f"{len(dataset.positive_dataset)} positive fields, "
                        f"{len(dataset.negative_variants)} negative variants ---"
                    )
                except Exception as exc:
                    self._log(
                        f"Test data generation failed for {scenario.scenario_id}: "
                        f"{type(exc).__name__}: {exc}",
                        level="error",
                    )

        new_datasets = [d for d in datasets if d is not None]
        self._log(f"Generated {len(new_datasets)} new dataset(s)")

        # Step 2.5 — Coverage signal. A dataset "covers" its scenario when it
        # has a real positive_dataset, or when having none is legitimate (no
        # negative_variants either — the read-only "nothing to test" case
        # validate_test_data treats as valid). An empty positive_dataset with
        # non-empty negative_variants is the inconsistent case that indicates
        # the LLM under-delivered for that scenario.
        covered = [d for d in new_datasets if d.positive_dataset or not d.negative_variants]
        coverage_pct = round(len(covered) / len(new_datasets) * 100) if new_datasets else 100
        coverage_warning = coverage_pct < 50
        if coverage_warning:
            self._log(
                f"Coverage warning — only {coverage_pct}% of scenarios got a "
                "usable positive dataset",
                level="warning",
            )

        # Step 3 — Validate
        valid_new, warnings = validate_test_data(new_datasets)
        for w in warnings:
            self._log(f"Validation: {w}", level="warning")

        # Step 4 — Merge + export
        existing_models = _reconstruct_existing(ctx.existing_test_data_raw)
        merged = existing_models + valid_new
        paths = export_test_data(merged, output_dir, project_name)
        for p in (paths or {}).values():
            self._log(f"Written: {p}")
        self._log(
            f"Done — {len(existing_models)} existing + {len(valid_new)} new "
            f"= {len(merged)} total dataset(s) exported"
        )

        return {
            "module": "testdata",
            "status": "success",
            "project": project_name,
            "scenarios_processed": len(uncovered),
            "datasets_generated": len(new_datasets),
            "datasets_valid": len(valid_new),
            "datasets_total": len(merged),
            "coverage_pct": coverage_pct,
            "coverage_warning": coverage_warning,
            "validation_warnings": warnings,
            "output": paths,
        }


# ── Module helpers ─────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"


def _reconstruct_existing(existing_raw: dict) -> List[ScenarioTestData]:
    models = []
    for record in existing_raw.values():
        try:
            models.append(ScenarioTestData.model_validate(record))
        except Exception:
            pass
    return models


def _load_fill_fields_from_catalog(catalog_path: str) -> dict:
    """
    Read interaction_catalog.json and return {scenario_id: [field_name, ...]}.

    Expected format (flexible — handles two common shapes):
      {"interactions": [{"scenario_id": "BS-001", "fills": ["fill_email", ...]}]}
      or a flat dict {"BS-001": {"fills": ["fill_email", ...]}}
    """
    if not os.path.exists(catalog_path):
        return {}
    try:
        with open(catalog_path, encoding="utf-8") as f:
            raw = json.load(f) or {}

        by_scenario: dict = {}

        # Shape 1: {"interactions": [...]}
        for entry in raw.get("interactions", []):
            sid = entry.get("scenario_id", "")
            if not sid:
                continue
            fills = entry.get("fills") or entry.get("fill_fields") or []
            if fills:
                by_scenario[sid] = fills

        # Shape 2: {"BS-001": {"fills": [...]}} or {"BS-001": {"steps": [...]}}
        for key, val in raw.items():
            if not key.startswith("BS-") or not isinstance(val, dict):
                continue
            fills = val.get("fills") or val.get("fill_fields") or []
            if fills and key not in by_scenario:
                by_scenario[key] = fills

        return by_scenario
    except Exception:
        return {}


def _load_fill_fields_from_intents(intents_path: str) -> dict:
    """Legacy loader for intents.yaml → {scenario_id: [fill_intent_name, ...]}."""
    import yaml
    if not os.path.exists(intents_path):
        return {}
    try:
        with open(intents_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        by_scenario: dict = {}
        for intent in raw.get("intents", []):
            if intent.get("action") == "fill":
                for sid in intent.get("source_scenarios", []):
                    by_scenario.setdefault(sid, []).append(intent["intent_name"])
        return by_scenario
    except Exception:
        return {}
