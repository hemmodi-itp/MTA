"""
ScriptGenerationAgent — generates TypeScript Playwright .spec.ts files.

One spec per business scenario. Reads scenario_element_map.json (from SemanticMapAgent)
so each LLM call receives only the 3-7 elements relevant to that scenario.

The LLM does NOT write Playwright code. It returns a JSON test plan built only
from a fixed action-verb vocabulary (ALLOWED_ACTIONS, mirroring
application_assets/_shared/runtime/ActionEngine.ts), named locator keys (this
project's locator_map.json — one flat file merged from every module's
dom_elements.json, never overwritten wholesale), and reusable named flows
(flows.json). A deterministic renderer (tools/test_creation/script_generator/
spec_renderer.py) turns the validated plan into the actual .spec.ts file — no
LLM-authored code ever reaches disk. Anything the plan can't express
(missing_actions / missing_locators) is flagged to human_review_queue.json
instead of guessed.

Locators are validated once per project per run (grouped by module) against a
live headless page, not once per scenario — a key that fails to resolve is
excluded from that module's scenarios' allowed_locators (never offered to the
LLM) and reported via record_locator_drift, rather than caught after a spec is
generated.

Failure routing (per-scenario, in _generate_spec — NOT via BaseAgent.execute_with_fallback):
    Tier 0 — primary LLM, plan-based
    Tier 1 — NSHTTPConnector / alt model, plan-based
    Tier 2 — Python deterministic (fallback_core) — gated by workflows/agent_registry.yaml:
             script_generation.fallbacks needing a connector_type: python_stub entry.
             Off by default: an unfixable scenario is skipped (left uncovered, retried
             next run) instead of getting a permanent test.skip() stub spec.

Output:
    test_creation/locator_map.json          (bootstrapped/merged once per project per run)
    test_creation/pages.ts                  (every module's Page class + PAGE_REGISTRY)
    test_creation/flows.generated.ts        (rebuilt from flows.json every run, if present)
    test_creation/test_plans.json           (validated JSON plan per scenario, tier 0/1 only)
    test_creation/test_scripts/{module_id}/test_{id}_{snake_title}.spec.ts  (one per scenario)
    test_creation/test_suite.json           (updated after every spec; gains generation_mode)
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from tools.state.review_queue import flag_missing_capability, record_locator_drift
from agents.test_creation.script_generation.prompt import ACTION_LIBRARY_PROMPT, LOCATOR_RECONCILE_PROMPT
from agents.test_creation.script_generation.tools import (
    LOCATOR_FIRST_ACTIONS,
    LOCATOR_OR_NULL_ACTIONS,
    VALUE_REQUIRED_ACTIONS,
    render_flows_module,
    render_spec_from_plan,
    update_catalog,
    write_named_locator_map,
    write_pages_module,
)
from connectors.connector_registry import ConnectorRegistry
from tools.config.agent_registry_config import fallback_enabled, python_stub_fallback_enabled
from tools.config.test_generation_config import DEFAULT_TEST_GENERATION_CONFIG, load_test_generation_config
from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.shared import get_logger
from tools.shared.llm_response_validator import parse_llm_json

# Mirrors application_assets/_shared/runtime/ActionEngine.ts's public verbs,
# plus the "useFlow" pseudo-action (a call into flows.generated.ts instead of
# a raw ActionEngine method). Keep these two lists in sync by hand — there is
# no single source of truth across the Python/TypeScript boundary.
ALLOWED_ACTIONS = frozenset({
    "navigate", "click", "doubleClick", "hover", "enterText", "clearAndEnterText",
    "pressKey", "checkCheckbox", "uncheckCheckbox", "selectDropdownByText",
    "selectDropdownByValue", "scrollIntoView", "waitForElement", "waitForTimeout",
    "dragAndDrop", "uploadFile", "verifyVisible", "verifyHidden", "verifyText",
    "verifyContainsText", "verifyValue", "verifyEnabled", "verifyDisabled",
    "verifyChecked", "verifyCount", "verifyUrl", "verifyUrlContains", "verifyTitle",
    "verifyTitleContains", "takeScreenshot", "goBack", "reload", "verifyNoPageErrors", "useFlow",
})


class ScriptGenerationAgent(BaseAgent):
    MODULE_NAME = "script_generation"

    def __init__(self, provider=None, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.script_generation")

    # ── Public entry point ─────────────────────────────────────────────────────

    def execute(self, request: dict, state: dict) -> Dict:
        """
        Generate TypeScript .spec.ts files for all uncovered business scenarios.

        Each scenario is processed independently — a failure on one scenario logs
        a warning and continues; it does NOT block the others.
        """
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        url = request.get("url", "")

        comprehension_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        test_creation_dir = os.path.join(_ASSETS_BASE, safe, "test_creation")
        scripts_dir = os.path.join(test_creation_dir, "test_scripts")
        test_data_path = os.path.join(test_creation_dir, "test_data", "test_data.json")
        sem_map_path = os.path.join(test_creation_dir, "scenario_element_map.json")
        scenarios_path = os.path.join(comprehension_dir, "business_scenarios.json")
        locator_map_path = os.path.join(test_creation_dir, "locator_map.json")
        pages_path = os.path.join(test_creation_dir, "pages.ts")
        flows_path = os.path.join(test_creation_dir, "flows.json")
        flows_generated_path = os.path.join(test_creation_dir, "flows.generated.ts")
        test_plans_path = os.path.join(test_creation_dir, "test_plans.json")
        project_dir = os.path.join(_ASSETS_BASE, safe)

        self._log(f"Starting — project='{project_name}'")

        # Fail fast if critical inputs are absent
        for path, label in [
            (scenarios_path, "business_scenarios.json"),
        ]:
            if not os.path.exists(path):
                from agents.common.failure_classifier import MissingInputError
                raise MissingInputError(f"{label} not found: {path}")

        scenarios = _load_scenarios(scenarios_path)
        scenario_map = _load_json_or_empty(sem_map_path)
        test_data_map = _load_test_data_map(test_data_path)

        drift_warning = _test_data_drift_warning(scenarios, test_data_map)
        if drift_warning:
            self._log(drift_warning, level="warning")

        coverage_warning = _scenario_element_map_coverage_warning(scenarios, scenario_map)
        if coverage_warning:
            self._log(coverage_warning, level="warning")

        os.makedirs(test_creation_dir, exist_ok=True)

        # Bootstrap/merge the project-wide named locator map from
        # dom_elements.json — never deletes or duplicates an existing key
        # (see build_named_locator_map's merge algorithm). Cheap no-op when
        # nothing in dom_elements.json has changed since the last run.
        llm_reconcile = self._make_llm_reconcile(request)
        map_drift = write_named_locator_map(comprehension_dir, locator_map_path, llm_reconcile=llm_reconcile)
        record_locator_drift(
            project_name, "_project",
            map_drift["added"], map_drift["updated"], map_drift["possibly_removed"],
            output_dir=project_dir, kind="locator_map_drift", source="build_named_locator_map",
        )
        locator_map = _load_json_or_empty(locator_map_path)
        reverse_locator_index = _reverse_locator_index(locator_map)

        # Build a per-module URL override / setup-steps / display-name map from
        # the modules list in the request (project.yaml's modules[]).
        module_url_map = {
            m["id"]: m["url"] for m in request.get("modules", []) if m.get("id") and m.get("url")
        }
        module_setup_map = {
            m["id"]: m["setup"] for m in request.get("modules", []) if m.get("id") and m.get("setup")
        }
        module_name_map = {
            m["id"]: m.get("name") for m in request.get("modules", []) if m.get("id")
        }

        # Regenerate the Page-factory classes fresh every run — pure codegen
        # from locator_map.json, so it's always in sync with a human/HealingAgent
        # repair to the map, without a separate merge step of its own.
        write_pages_module(locator_map, pages_path, module_names=module_name_map)

        # Rebuild flows.generated.ts from flows.json every run — cheap,
        # deterministic, and keeps it in sync if a human edits flows.json.
        flows = _load_json_or_empty(flows_path)
        flows_meta = {name: f.get("params", []) for name, f in flows.items()}
        if flows:
            flows_ts = render_flows_module(flows, safe)
            with open(flows_generated_path, "w", encoding="utf-8") as f:
                f.write(flows_ts)

        # Resolve BASE_URL from project.yaml if not in request
        if not url:
            url = _load_base_url(safe)

        # One-time-per-project (grouped by module) live validation of the
        # locator map — replaces the old per-scenario live dry-run at a
        # fraction of the browser-launch cost, same protection.
        unresolvable_keys = self._validate_locator_map_live(
            project_name, safe, locator_map, url, module_url_map, module_setup_map
        )

        # Load existing suite to know which specs are already generated.
        # Also verify the spec file actually exists on disk — if it was deleted
        # the registry entry is stale and the spec must be regenerated.
        suite_path = os.path.join(test_creation_dir, "test_suite.json")
        suite = _load_suite(suite_path)
        existing_spec_ids = {
            s["spec_id"]
            for s in suite.get("specs", [])
            if s.get("file") and os.path.exists(os.path.join(scripts_dir, s["file"]))
        }

        uncovered = [s for s in scenarios if s.get("scenario_id") not in existing_spec_ids]
        self._log(
            f"{len(existing_spec_ids)} spec(s) already exist on disk — "
            f"{len(uncovered)} to generate"
        )

        if not uncovered:
            return {
                "module": "script_generation",
                "status": "success",
                "project": project_name,
                "scenarios_processed": 0,
                "scripts_generated": 0,
                "skipped": True,
                "reason": "all_scenarios_already_have_specs",
                "output": {"scripts_dir": scripts_dir, "test_suite": suite_path},
            }

        os.makedirs(scripts_dir, exist_ok=True)
        generated = []
        warnings = []
        test_plans = _load_json_or_empty(test_plans_path)

        for scenario in uncovered:
            sid = scenario.get("scenario_id", "")
            title = scenario.get("title", scenario.get("scenario_name", sid))
            module_id = _resolve_target_module_id(scenario.get("module_id"), request)
            if module_id is None:
                msg = (
                    f"no module context available for {sid} (scenario has no "
                    "module_id, no --module filter is active, and project.yaml "
                    "declares no modules) — refusing to write into the flat "
                    "test_scripts/ root"
                )
                self._log(f"FAIL — {msg}", level="error")
                warnings.append(f"{sid}: {msg}")
                continue
            module_name = scenario.get("module_name") or module_name_map.get(module_id)
            self._log(f"Generating spec for {sid}: {title} [{module_id}]")

            elements = _get_elements_for_scenario(sid, scenario_map)
            test_data = test_data_map.get(sid, {})
            allowed_locators = _allowed_locator_entries_for_scenario(
                elements, reverse_locator_index, locator_map, unresolvable_keys
            )

            effective_url = module_url_map.get(module_id, url)
            gen_config = load_test_generation_config(safe, module_id=module_id)

            # Use per-scenario fallback routing — a failure on one spec (whether
            # in generation, rendering, or writing) should not abort the rest,
            # so the whole per-scenario body is caught and recorded rather than
            # left to propagate out of the loop and fail the entire run.
            try:
                kind, payload, tier_used, fallback_route = self._generate_spec(
                    request=request,
                    scenario=scenario,
                    allowed_locators=allowed_locators,
                    test_data=test_data,
                    base_url=effective_url,
                    gen_config=gen_config,
                    flows_meta=flows_meta,
                    locator_map=locator_map,
                )

                filename = _spec_filename(sid, title)
                # Every spec is module-scoped — module_id is resolved (never None)
                # above, so this never writes into the flat test_scripts/ root.
                module_scripts_dir = os.path.join(scripts_dir, module_id)
                os.makedirs(module_scripts_dir, exist_ok=True)
                spec_path = os.path.join(module_scripts_dir, filename)
                relative_file = f"{module_id}/{filename}"
                spec_rel_path = os.path.join("projects", safe, "test_creation", "test_scripts", relative_file)

                generation_mode = None
                if kind == "plan":
                    plan = payload
                    missing_actions = plan.get("missing_actions") or []
                    missing_locators = plan.get("missing_locators") or []
                    flag_missing_capability(
                        project_name, sid, missing_actions, missing_locators, output_dir=project_dir,
                    )
                    if missing_actions or missing_locators:
                        self._log(
                            f"{sid}: flagged {len(missing_actions)} missing action(s), "
                            f"{len(missing_locators)} missing locator(s) for human review",
                            level="warning",
                        )

                    if not plan.get("tests"):
                        self._log(f"{sid}: plan has no tests the action library can express — skipping", level="warning")
                        warnings.append(f"{sid}: no expressible tests (see human_review_queue.json)")
                        continue

                    spec_content = render_spec_from_plan(
                        plan, scenario, effective_url, spec_rel_path,
                        project=safe, flows_meta=flows_meta,
                    )
                    generation_mode = "action_library"
                    test_plans[sid] = plan
                else:  # kind == "raw" — legacy tier-2 Python fallback, unchanged
                    spec_content = payload

                module_setup = module_setup_map.get(module_id)
                if module_setup:
                    spec_content = _inject_setup_steps(spec_content, module_setup)
                    self._log(f"{sid}: injected {len(module_setup)} setup step(s) from module '{module_id}'")

                with open(spec_path, "w", encoding="utf-8") as f:
                    f.write(spec_content)
                self._log(f"Written: {spec_path} (tier={tier_used})")

                spec_entry = {
                    "spec_id": sid,
                    "module_id": module_id,
                    "module_name": module_name,
                    "scenario_title": title,
                    "file": relative_file,
                    "status": "new" if tier_used == 0 else "degraded_fallback",
                    "tier_used": tier_used,
                    "fallback_route": fallback_route,
                    "generation_mode": generation_mode,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "last_run": None,
                    "last_result": None,
                }
                _upsert_spec(suite, spec_entry)
                _write_suite(suite, suite_path, project_name)
                if generation_mode == "action_library":
                    _write_test_plans(test_plans, test_plans_path)

                generated.append(relative_file)
            except Exception as exc:
                self._log(f"FAIL — {sid}: {exc}", level="error")
                warnings.append(f"{sid}: {exc}")
                continue

        self._log(f"Done — {len(generated)} spec(s) written, {len(warnings)} failure(s)")

        # Refresh the human-readable catalog (test_catalog.csv/.md) from the
        # updated business_scenarios.json + test_suite.json. A catalog-write
        # failure must never fail generation itself.
        try:
            update_catalog(project_name)
        except Exception as exc:
            self._log(f"Catalog update failed (non-fatal): {exc}", level="warning")

        return {
            "module": "script_generation",
            "status": "success" if not warnings else "partial",
            "project": project_name,
            "scenarios_processed": len(uncovered),
            "scripts_generated": len(generated),
            "warnings": warnings,
            "output": {"scripts_dir": scripts_dir, "test_suite": suite_path},
        }

    # ── Per-scenario generation with fallback routing ─────────────────────────

    def _generate_spec(
        self,
        request: dict,
        scenario: dict,
        allowed_locators: List[Dict[str, str]],
        test_data: dict,
        base_url: str,
        flows_meta: Dict[str, List[str]],
        gen_config: Optional[dict] = None,
        locator_map: Optional[Dict[str, dict]] = None,
    ):
        """
        Returns (kind, payload, tier_used, fallback_route).

        kind == "plan": payload is a validated JSON test plan (tier 0/1) — the
            caller renders it via spec_renderer.render_spec_from_plan.
        kind == "raw": payload is a complete .spec.ts string, produced by the
            unchanged legacy Python fallback (tier 2) — written as-is.

        Applies FailureClassifier internally per-scenario rather than routing the
        entire execute() call through execute_with_fallback — this keeps a single
        bad scenario from halting the whole run.
        """
        import time
        from agents.common import failure_classifier as fc

        gen_config = gen_config or dict(DEFAULT_TEST_GENERATION_CONFIG)
        allowed_keys = {e["key"] for e in allowed_locators}
        attempt = 0
        current_connector = None
        current_model = None

        while True:
            try:
                if current_connector == "ns_http":
                    plan = self._plan_via_ns(request, scenario, allowed_locators, test_data, base_url)
                    _validate_plan(plan, scenario.get("scenario_id", ""), ALLOWED_ACTIONS, allowed_keys, flows_meta)
                    plan, dropped = _drop_placeholder_negative_tests(plan, test_data)
                    if dropped:
                        self._log(
                            f"{scenario.get('scenario_id')}: dropped {len(dropped)} "
                            f"placeholder negative test(s) with no basis in test_data "
                            f"({', '.join(dropped)})",
                            level="warning",
                        )
                    plan, mismatched = _flag_action_locator_type_mismatches(plan, locator_map or {})
                    if mismatched:
                        self._log(
                            f"{scenario.get('scenario_id')}: dropped {len(mismatched)} "
                            f"action/locator-type mismatch(es) ({'; '.join(mismatched)})",
                            level="warning",
                        )
                    return "plan", plan, 1, None
                elif current_model is not None:
                    plan = self._plan_via_llm(
                        scenario, allowed_locators, test_data, base_url, flows_meta,
                        llm=self._alt_llm(current_model, request),
                        gen_config=gen_config,
                        locator_map=locator_map,
                    )
                    return "plan", plan, 1, None
                else:
                    llm = self._registry.get_llm(request.get("connector_mode"))
                    plan = self._plan_via_llm(
                        scenario, allowed_locators, test_data, base_url, flows_meta,
                        llm=llm, gen_config=gen_config, locator_map=locator_map,
                    )
                    return "plan", plan, 0, None

            except Exception as exc:
                route = fc.classify(exc, attempt)
                self._log(
                    f"{scenario.get('scenario_id')} attempt={attempt} route={route} "
                    f"exc={type(exc).__name__}: {exc}",
                    level="warning",
                )

                if route == fc.FAIL_FAST:
                    raise

                if route == fc.RETRY:
                    time.sleep(min(2 ** attempt, 30))
                    attempt += 1
                    continue

                if route == fc.NS_HTTP:
                    if not fallback_enabled("script_generation", "ns_http", self.settings):
                        raise RuntimeError(
                            f"{scenario.get('scenario_id')}: primary generation failed "
                            f"({type(exc).__name__}: {exc}) and the 'ns_http' fallback tier "
                            "is disabled for script_generation in workflows/agent_registry.yaml "
                            "— failing rather than rerouting"
                        ) from exc
                    current_connector = "ns_http"
                    attempt += 1
                    continue

                if route == fc.ALT_MODEL:
                    if not fallback_enabled("script_generation", "alt_model", self.settings):
                        raise RuntimeError(
                            f"{scenario.get('scenario_id')}: primary generation failed "
                            f"({type(exc).__name__}: {exc}) and the 'alt_model' fallback tier "
                            "is disabled for script_generation in workflows/agent_registry.yaml "
                            "— failing rather than switching models"
                        ) from exc
                    current_model = "claude-haiku-4-5-20251001"
                    attempt += 1
                    continue

                if route in (fc.FALLBACK, fc.HUMAN_REVIEW):
                    if route == fc.HUMAN_REVIEW:
                        self._flag_for_human_review(request, exc)
                    if not python_stub_fallback_enabled("script_generation", self.settings):
                        raise RuntimeError(
                            f"{scenario.get('scenario_id')}: primary generation exhausted "
                            f"all retries/reroutes ({type(exc).__name__}: {exc}) and the "
                            "Python stub fallback is disabled for script_generation in "
                            "workflows/agent_registry.yaml — skipping rather than writing "
                            "a stub spec"
                        ) from exc
                    content = self._spec_via_fallback(scenario, [], test_data, base_url)
                    return "raw", content, 2, route

                raise RuntimeError(f"Unhandled route '{route}'") from exc

    def _plan_via_llm(
        self,
        scenario: dict,
        allowed_locators: List[Dict[str, str]],
        test_data: dict,
        base_url: str,
        flows_meta: Dict[str, List[str]],
        llm,
        gen_config: Optional[dict] = None,
        locator_map: Optional[Dict[str, dict]] = None,
    ) -> dict:
        sid = scenario.get("scenario_id", "")
        gen_config = gen_config or dict(DEFAULT_TEST_GENERATION_CONFIG)

        flows_summary = {name: {"params": params} for name, params in flows_meta.items()}
        distinct_clusters = {e["cluster"] for e in allowed_locators if e.get("cluster")}
        cluster_count = len(distinct_clusters) or 1

        prompt = ACTION_LIBRARY_PROMPT.safe_substitute(
            scenario_json=json.dumps(scenario, ensure_ascii=False, indent=2),
            test_data_json=json.dumps(test_data, ensure_ascii=False, indent=2),
            base_url=base_url or "http://localhost:3000",
            valid_actions_json=json.dumps(sorted(ALLOWED_ACTIONS), ensure_ascii=False, indent=2),
            valid_locators_json=json.dumps(allowed_locators, ensure_ascii=False, indent=2),
            valid_flows_json=json.dumps(flows_summary, ensure_ascii=False, indent=2),
            max_negative_cases=gen_config["max_negative_cases"],
            max_boundary_cases=gen_config["max_boundary_cases"],
            max_data_iterations=gen_config["max_data_iterations"],
            distinct_cluster_count=cluster_count,
        )

        raw = llm.generate(prompt)
        plan = _parse_plan_json(raw, sid)
        allowed_keys = {e["key"] for e in allowed_locators}
        _validate_plan(plan, sid, ALLOWED_ACTIONS, allowed_keys, flows_meta)
        plan, dropped = _drop_placeholder_negative_tests(plan, test_data)
        if dropped:
            self._log(
                f"{sid}: dropped {len(dropped)} placeholder negative test(s) with no "
                f"basis in test_data ({', '.join(dropped)})",
                level="warning",
            )
        plan, mismatched = _flag_action_locator_type_mismatches(plan, locator_map or {})
        if mismatched:
            self._log(
                f"{sid}: dropped {len(mismatched)} action/locator-type mismatch(es) "
                f"({'; '.join(mismatched)})",
                level="warning",
            )
        return plan

    def _plan_via_ns(
        self,
        request: dict,
        scenario: dict,
        allowed_locators: List[Dict[str, str]],
        test_data: dict,
        base_url: str,
    ) -> dict:
        ns = self._registry.get_ns()
        sid = scenario.get("scenario_id", "")
        self._log(f"NS fallback for {sid}")
        result = ns.call("script_generation_agent", {
            "project_name": request.get("project_name", ""),
            "scenario_id": sid,
        })
        plan = result.get("plan")
        if not plan:
            from agents.common.failure_classifier import LLMResponseValidationError
            raise LLMResponseValidationError(
                f"NS agent returned no 'plan' for {sid}"
            )
        return plan

    def _spec_via_fallback(
        self,
        scenario: dict,
        elements: list,
        test_data: dict,
        base_url: str,
    ) -> str:
        from agents.common import fallback_core
        self._log(
            f"Python fallback for {scenario.get('scenario_id')} — "
            "1 positive test + skip stubs"
        )
        return fallback_core.fallback_generate_script(
            scenario=scenario,
            elements=elements,
            test_data=test_data,
            base_url=base_url,
        )

    # ── BaseAgent tier overrides (for execute_with_fallback compatibility) ─────
    # _run_primary is intentionally not overridden — BaseAgent's default
    # (self.execute(request, state)) is already correct here, since execute()
    # handles the full per-scenario routing/fallback loop itself.

    def _run_py_fallback(self, request: dict, state: dict) -> Dict:
        return {
            "module": "script_generation",
            "status": "degraded",
            "error": "Python fallback at agent level — per-scenario fallbacks are preferred",
            "fallback_route": "fallback",
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _flag_for_human_review(self, request: dict, exc: Exception) -> None:
        from tools.state.review_queue import flag_for_human_review
        project_name = request.get("project_name", "project")
        flag_for_human_review(
            project_name, "script_generation", request, exc,
            output_dir=os.path.join(_ASSETS_BASE, _safe_name(project_name)),
        )

    def _make_llm_reconcile(self, request: dict):
        """Returns a callable build_named_locator_map can hand its ambiguous
        add/remove remainder to — never called for the deterministic fast
        path (id match or identical-locator match), only when a rescan has
        both unmatched new elements and existing entries whose source
        element disappeared. Failures here just mean "mint a new key",
        never a hard error."""
        def _reconcile(new_elements: List[dict], removed_candidates: List[dict]) -> Dict[str, str]:
            try:
                llm = self._registry.get_llm(request.get("connector_mode"))
            except Exception as exc:
                self.logger.warning(f"Locator reconciliation LLM unavailable: {exc}")
                return {}
            prompt = LOCATOR_RECONCILE_PROMPT.safe_substitute(
                new_elements_json=json.dumps(new_elements, ensure_ascii=False, indent=2),
                removed_candidates_json=json.dumps(removed_candidates, ensure_ascii=False, indent=2),
            )
            try:
                raw = llm.generate(prompt)
                mapping = parse_llm_json(raw)
                return mapping if isinstance(mapping, dict) else {}
            except Exception as exc:
                self.logger.warning(f"Locator reconciliation LLM call failed: {exc}")
                return {}
        return _reconcile

    def _validate_locator_map_live(
        self,
        project_name: str,
        safe: str,
        locator_map: Dict[str, dict],
        url: str,
        module_url_map: Dict[str, str],
        module_setup_map: Dict[str, list],
    ) -> set:
        """Once per project per run, grouped by module (one browser launch
        per module, not per scenario): verify every locator_map.json entry
        actually resolves on a live page. Returns the set of keys that
        failed — the caller excludes them from allowed_locators so the LLM
        is never offered a known-dead key — and reports them via
        record_locator_drift. A module whose page can't be reached at all
        is skipped entirely (never treated as "every key is dead")."""
        by_module: Dict[str, List[str]] = {}
        for key, entry in locator_map.items():
            by_module.setdefault(entry.get("_module_id") or "_default", []).append(key)

        unresolvable: set = set()
        for module_id, keys in by_module.items():
            effective_url = module_url_map.get(module_id, url)
            scanner, page = self._get_validation_page(module_id, effective_url, module_setup_map)
            if page is None:
                continue
            dead_keys = []
            try:
                for key in keys:
                    try:
                        if not self._locator_entry_resolves(page, locator_map[key]):
                            dead_keys.append(key)
                    except Exception as exc:
                        self.logger.warning(f"Locator dry-run check errored for '{key}': {exc}")
            finally:
                if scanner is not None:
                    try:
                        scanner.close()
                    except Exception:
                        pass
            if dead_keys:
                unresolvable.update(dead_keys)
                record_locator_drift(
                    project_name, module_id, added=[], updated=[], possibly_removed=dead_keys,
                    output_dir=os.path.join(_ASSETS_BASE, safe),
                    kind="locator_map_drift", source="live_validation",
                )
        return unresolvable

    def _get_validation_page(
        self, module_id: str, effective_url: str, module_setup_map: Dict[str, list],
    ):
        """Lazily launch one headless page for this module's live locator
        dry-run checks. Returns (scanner, page), both None if a browser
        genuinely can't be launched — callers must treat that as "can't
        verify", not a rejection."""
        try:
            from tools.playwright_scanner import PlaywrightScanner
            scanner = PlaywrightScanner(headless=True)
            page = scanner.launch()
            setup = module_setup_map.get(module_id)
            if setup:
                scanner._execute_setup_steps(page, setup)
            if effective_url:
                page.goto(effective_url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
            return scanner, page
        except Exception as exc:
            self._log(f"Locator dry-run unavailable for module '{module_id}': {exc}", level="warning")
            return None, None

    @staticmethod
    def _locator_entry_resolves(page, entry: dict) -> bool:
        t = entry.get("type")
        v = entry.get("locator", "")
        name = entry.get("name")
        try:
            if t == "css":
                locator = page.locator(v)
            elif t == "xpath":
                locator = page.locator(f"xpath={v}")
            elif t == "role":
                locator = page.get_by_role(v, name=name) if name else page.get_by_role(v)
            elif t == "text":
                locator = page.get_by_text(v)
            elif t == "label":
                locator = page.get_by_label(v)
            elif t == "testid":
                locator = page.get_by_test_id(v)
            elif t == "placeholder":
                locator = page.get_by_placeholder(v)
            else:
                return True  # unknown type — can't check, don't reject
            # Exactly 1, not just >0: a locator matching 2+ elements (e.g. two
            # "Sign in" buttons — one text, one icon, shown responsively) is a
            # Playwright strict-mode violation at actual runtime just as
            # surely as matching 0 — the real SC-001/SC-003 failures passed
            # this check under the old ">0" test and were only caught live.
            return locator.count() == 1
        except Exception:
            return True  # a resolution error is "can't tell", not a rejection

    def _alt_llm(self, model: str, request: dict):
        try:
            from connectors.llm.claude import ClaudeConnector
            return ClaudeConnector(model=model)
        except TypeError:
            return self._registry.get_llm("external")


# ── Module-level helpers ────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"


def _spec_filename(scenario_id: str, title: str) -> str:
    snake = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"test_{scenario_id}_{snake}.spec.ts"


def _load_scenarios(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        raw = raw.get("scenarios", raw.get("business_scenarios", []))
    return raw if isinstance(raw, list) else []


def _load_json_or_empty(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f) or {}


def _load_test_data_map(path: str) -> Dict[str, Any]:
    """Return {scenario_id: test_data_record} from test_data.json."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {r.get("scenario_id", ""): r for r in raw if r.get("scenario_id")}
    if isinstance(raw, dict):
        return raw
    return {}


def _test_data_drift_warning(
    scenarios: List[Dict[str, Any]], test_data_map: Dict[str, Any],
) -> Optional[str]:
    """Detect the AWS_Test class of bug: test_data.json has real records, but
    every one of them uses a scenario-id scheme (e.g. legacy "SC-001") that
    no longer matches current business_scenarios.json ids (e.g.
    "M01_BS_001") — every _load_test_data_map(sid) lookup then silently
    misses and scripts generate with test_data={}, even though rich test
    data technically exists on disk. Returns a warning message, or None if
    there's nothing to flag (no data, no scenarios, or at least one id
    overlaps)."""
    if not test_data_map or not scenarios:
        return None
    current_ids = {s.get("scenario_id") for s in scenarios if s.get("scenario_id")}
    if not current_ids or not current_ids.isdisjoint(test_data_map.keys()):
        return None
    return (
        f"test_data.json has {len(test_data_map)} record(s) but NONE of their "
        f"scenario_ids match current business_scenarios.json ({len(current_ids)} "
        "scenario(s)) — test_data.json is likely stale (e.g. an old scenario-id "
        "scheme) and every scenario will generate with test_data={}. Rerun "
        "TestDataAgent for this project."
    )


def _scenario_element_map_coverage_warning(
    scenarios: List[Dict[str, Any]], scenario_map: Dict[str, Any],
) -> Optional[str]:
    """Detect the geminiTest class of bug: business_scenarios.json grew (a
    later ComprehensionAgent/BRD run added real scenarios) but
    scenario_element_map.json was never regenerated against the current
    scenario list — SemanticMapAgent maps ALL scenarios every run with no
    incremental skip, so this only happens when semantic_map simply wasn't
    rerun after scenarios changed. Every missing scenario_id then gets zero
    relevant_elements, so ScriptGenerationAgent has no locators to work with
    and produces near-empty specs (often just `navigate()` alone) with no
    signal why. Returns a warning message, or None if scenario_map is empty
    (nothing has mapped anything yet, or a BRD-only project with no
    locators at all — an already-documented, different situation) or every
    current scenario has at least an entry (however few elements)."""
    if not scenario_map or not scenarios:
        return None
    current_ids = {s.get("scenario_id") for s in scenarios if s.get("scenario_id")}
    missing = current_ids - scenario_map.keys()
    if not missing:
        return None
    sample = ", ".join(sorted(missing)[:5]) + ("..." if len(missing) > 5 else "")
    return (
        f"{len(missing)}/{len(current_ids)} scenario(s) in business_scenarios.json have NO "
        f"entry at all in scenario_element_map.json ({sample}) — semantic_map likely wasn't "
        "rerun after business_scenarios.json changed. Every one of these will generate with "
        "zero locators available. Rerun SemanticMapAgent for this project."
    )


def _resolve_target_module_id(scenario_module_id: Optional[str], request: dict) -> Optional[str]:
    """Every generated spec must land under a module folder — test_scripts/
    must never get a flat, non-module file again. Prefer the scenario's own
    module_id; a scenario with none (e.g. a legacy pre-module scenario) is
    adopted into whichever module this run is actively targeting instead —
    the --module filter (request["module_filter"]), or, if the run wasn't
    narrowed to one module, the narrowed/declared modules[] list's first
    entry. Returns None only if the run has no module context whatsoever
    (no filter, no modules declared) — callers must skip the scenario
    rather than fall back to a flat path."""
    if scenario_module_id:
        return scenario_module_id
    if request.get("module_filter"):
        return request["module_filter"]
    modules = request.get("modules") or []
    if modules and isinstance(modules[0], dict) and modules[0].get("id"):
        return modules[0]["id"]
    return None


# ── Named locator lookup for prompts ────────────────────────────────────────
#
# scenario_element_map.json's relevant_elements carry a locator_id (LOC-XXXX)
# — the id build_dom_locator_map.py assigns during discovery. The action-based
# prompt needs the human-readable locator_map.json key instead, so the LLM can
# reference a name a human/renderer both understand.

def _reverse_locator_index(locator_map: dict) -> Dict[str, str]:
    """Map each locator_map.json entry's _source_locator_id back to its key."""
    return {
        entry.get("_source_locator_id"): key
        for key, entry in locator_map.items()
        if entry.get("_source_locator_id")
    }


def _allowed_locator_entries_for_scenario(
    elements: list,
    reverse_index: Dict[str, str],
    locator_map: dict,
    unresolvable_keys: Optional[set] = None,
) -> List[Dict[str, str]]:
    """Return [{key, description, ...}] for this scenario's relevant
    elements, restricted to keys that actually exist in locator_map.json and
    passed the live validation pass (excludes any key in unresolvable_keys,
    so the LLM is never offered a known-dead locator).

    When SemanticMapAgent enriched this scenario's relevant_elements with
    intent-level fields (action/expected_result/cluster/confidence — see
    semantic_map/tools.py:enrich_relevant_elements), those pass through too,
    so the prompt can prioritize by cluster/confidence instead of treating
    every locator as equally relevant. Absent for BRD-only projects (no
    dom_intents.json to enrich from) — every key here stays optional."""
    unresolvable_keys = unresolvable_keys or set()
    result = []
    seen = set()
    for el in elements:
        loc_id = el.get("locator_id")
        key = reverse_index.get(loc_id)
        if key and key not in seen and key not in unresolvable_keys:
            seen.add(key)
            entry = {"key": key, "description": locator_map.get(key, {}).get("description", "")}
            for field in ("action", "expected_result", "cluster", "confidence"):
                if el.get(field) is not None:
                    entry[field] = el[field]
            result.append(entry)
    return result


def _get_elements_for_scenario(sid: str, scenario_map: dict) -> List[Dict[str, Any]]:
    """Return relevant_elements list for a scenario, or [] if not in map."""
    entry = scenario_map.get(sid, {})
    return entry.get("relevant_elements", [])


def _load_base_url(safe_project: str) -> str:
    """Try to read URL from project.yaml."""
    import yaml
    yaml_path = os.path.join(_ASSETS_BASE, safe_project, "project.yaml")
    if not os.path.exists(yaml_path):
        return ""
    try:
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("url", "")
    except Exception:
        return ""


def _parse_plan_json(raw: str, scenario_id: str) -> dict:
    """Parse the LLM's JSON plan (one outer markdown fence tolerated) via the shared
    tools/shared/llm_response_validator; any failure is an LLMResponseValidationError
    so failure_classifier routes it like every other malformed LLM response."""
    from agents.common.failure_classifier import LLMResponseValidationError
    try:
        plan = parse_llm_json(raw)
    except ValueError as exc:
        raise LLMResponseValidationError(f"{scenario_id}: LLM response is not valid JSON: {exc}") from exc
    if not isinstance(plan, dict):
        raise LLMResponseValidationError(f"{scenario_id}: plan must be a JSON object")
    return plan


# ── Plan validation ──────────────────────────────────────────────────────────
#
# The prompt already tells the LLM to use ONLY the provided actions/locator
# keys/flows (and to report anything else under missing_actions/
# missing_locators instead of guessing), but that's an instruction with zero
# enforcement on its own. This is the actual gate: every action must be in
# ALLOWED_ACTIONS, every locator_key must be a real locator_map.json key
# offered for this scenario, and every "useFlow" must reference a real
# flows.json entry — a plain dictionary/set-membership check, no live
# browser needed (that already happened once per project, up-front).

def _validate_plan(
    plan: dict,
    scenario_id: str,
    allowed_actions: frozenset,
    allowed_keys: set,
    allowed_flows: Dict[str, List[str]],
) -> None:
    from agents.common.failure_classifier import LLMResponseValidationError

    if "tests" not in plan or not isinstance(plan["tests"], list):
        raise LLMResponseValidationError(f"{scenario_id}: plan missing 'tests' list")

    for missing_field in ("missing_actions", "missing_locators"):
        if missing_field in plan and not isinstance(plan[missing_field], list):
            raise LLMResponseValidationError(f"{scenario_id}: '{missing_field}' must be a list")

    for test in plan["tests"]:
        if not isinstance(test, dict) or "name" not in test or "steps" not in test:
            raise LLMResponseValidationError(f"{scenario_id}: test entry missing 'name'/'steps'")
        if not isinstance(test["steps"], list) or not test["steps"]:
            raise LLMResponseValidationError(f"{scenario_id}: test '{test.get('name')}' has no steps")

        for step in test["steps"]:
            action = step.get("action") if isinstance(step, dict) else None
            if action not in allowed_actions:
                raise LLMResponseValidationError(
                    f"{scenario_id}: step uses disallowed action '{action}'"
                )

            if action == "useFlow":
                flow = step.get("flow")
                if flow not in allowed_flows:
                    raise LLMResponseValidationError(
                        f"{scenario_id}: step references unknown flow '{flow}'"
                    )
                continue

            if action == "dragAndDrop":
                for field in ("locator_key", "target_locator_key"):
                    key = step.get(field)
                    if key not in allowed_keys:
                        raise LLMResponseValidationError(
                            f"{scenario_id}: dragAndDrop references disallowed locator_key '{key}'"
                        )
                continue

            if action in LOCATOR_FIRST_ACTIONS:
                key = step.get("locator_key")
                if key not in allowed_keys:
                    raise LLMResponseValidationError(
                        f"{scenario_id}: step '{action}' references disallowed locator_key '{key}'"
                    )
            elif action in LOCATOR_OR_NULL_ACTIONS:
                key = step.get("locator_key")
                if key is not None and key not in allowed_keys:
                    raise LLMResponseValidationError(
                        f"{scenario_id}: step '{action}' references disallowed locator_key '{key}'"
                    )
            # else: a NO_LOCATOR_ACTIONS entry — no locator_key to validate.

            # spec_renderer's ARG_BUILDERS does a hard step["value"] for these
            # actions (see VALUE_REQUIRED_ACTIONS) — catch a missing value here,
            # while this can still route through retry/fallback, instead of
            # crashing render_spec_from_plan after validation already passed.
            if action in VALUE_REQUIRED_ACTIONS and step.get("value") is None:
                raise LLMResponseValidationError(
                    f"{scenario_id}: step '{action}' is missing required 'value' field"
                )


# ── Verification contract: no fabricated negative-test assertions ─────────────
#
# Concrete bug this guards against: a "negative" test generated for a plain
# nav-menu click (no real invalid-input pathway) asserted
# verifyText(..., "", "Page heading should be empty indicating failed load")
# — a placeholder that trivially passes regardless of real app behavior,
# since nothing in the scenario or test_data ever produces an empty heading.
# Per the verification contract (script_generation/agent.md): only fill a
# scenario's negative slot from intents whose test_data actually has a real
# expected_error: an LLM-authored "negative" test that has no such basis and
# whose only assertions are hardcoded empty-string checks is dropped rather
# than rendered — flagged via a warning log, not a hard failure, since the
# rest of the plan (positive/boundary tests) is still good.

def _drop_placeholder_negative_tests(
    plan: dict, test_data: dict,
) -> Tuple[dict, List[str]]:
    """Strip any "negative"-typed test whose only assertions are a hardcoded
    empty-string value, when this scenario's test_data has no real
    expected_error anywhere to justify one. Returns (possibly-updated plan,
    names of dropped tests)."""
    has_real_expected_error = any(
        bool(it.get("expected_error"))
        for variant in (test_data.get("negative_variants") or [])
        for it in (variant.get("iterations") or [])
    )
    if has_real_expected_error:
        return plan, []

    tests = plan.get("tests") or []
    kept: List[dict] = []
    dropped: List[str] = []
    for test in tests:
        verify_steps = [
            s for s in test.get("steps", [])
            if isinstance(s, dict) and str(s.get("action", "")).startswith("verify")
        ]
        is_placeholder = (
            test.get("type") == "negative"
            and bool(verify_steps)
            and all(s.get("value") == "" for s in verify_steps)
        )
        if is_placeholder:
            dropped.append(test.get("name", "unnamed"))
            continue
        kept.append(test)

    if dropped:
        plan = dict(plan)
        plan["tests"] = kept
    return plan, dropped


# ── Action/locator-type mismatch guard ────────────────────────────────────────
#
# Concrete bug this guards against: a prompt-textarea intent had no dedicated
# locator ever discovered (see dom_scan.py's identity-collision fix), so
# SemanticMapAgent/the LLM substituted the nearest available locator_key — the
# page's microphone button — and every enterText step aimed at it, filling
# nothing (a button isn't fillable) across 9+ scenarios on a real project.
# _validate_plan already guards "is this locator_key allowed", not "is this
# locator_key even the right KIND of element for this action" — this closes
# that gap for the clearest, highest-confidence case: a role-typed locator
# whose role is definitively not fillable (button/link/checkbox/etc.).
_NON_FILLABLE_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "tab", "menuitem",
    "menuitemcheckbox", "menuitemradio", "switch",
})
_FILL_ACTIONS = frozenset({"enterText", "clearAndEnterText"})


def _flag_action_locator_type_mismatches(
    plan: dict, locator_map: Dict[str, dict],
) -> Tuple[dict, List[str]]:
    """Drop (not render) any enterText/clearAndEnterText step whose
    locator_key resolves to a role-typed, definitively non-fillable element
    (button/link/checkbox/...). Only judges role-typed entries — a css-typed
    entry's actual element kind isn't knowable without a live DOM query
    (that's what _validate_locator_map_live already does separately), so
    this stays a targeted, high-confidence check rather than a guess.
    Returns (possibly-updated plan, list of dropped step descriptions)."""
    tests = plan.get("tests") or []
    dropped: List[str] = []
    kept_tests: List[dict] = []
    for test in tests:
        steps = test.get("steps") or []
        kept_steps = []
        for step in steps:
            if isinstance(step, dict) and step.get("action") in _FILL_ACTIONS:
                key = step.get("locator_key")
                entry = locator_map.get(key) or {}
                if entry.get("type") == "role" and entry.get("locator") in _NON_FILLABLE_ROLES:
                    dropped.append(
                        f"{test.get('name', 'unnamed')}: {step['action']}('{key}') — "
                        f"'{key}' is a {entry['locator']}, not a fillable field"
                    )
                    continue
            kept_steps.append(step)

        if steps and not kept_steps:
            # Every step in this test was dropped — the per-step message(s)
            # above already explain why; excluding the now-empty test needs
            # no separate message of its own.
            continue
        if kept_steps != steps:
            test = dict(test)
            test["steps"] = kept_steps
        kept_tests.append(test)

    if dropped:
        plan = dict(plan)
        plan["tests"] = kept_tests
    return plan, dropped


# ── Module setup injection (e.g. login before inventory/M02+ tests) ───────────
#
# project.yaml modules[].setup declares a goto/fill/click/wait sequence that
# tools/playwright_scanner.py already runs before DOM-scanning a module. That
# sequence is the module's real "how do I get to a usable state" — e.g. log in
# before testing the inventory page. Generated specs never reused it, so a
# module like inventory (M02) that requires auth would goto() straight into an
# unauthenticated redirect and every test would fail. Reuse the same schema
# here, deterministically (not LLM-prompted), so it applies no matter which
# tier (LLM / NS / Python fallback) produced the test bodies, and regardless
# of whether the file uses the per-test `{ action }` fixture (current LLM
# tier) or a shared outer `page` (legacy/fallback-tier specs).

_DESCRIBE_OPEN_RE = re.compile(r"test\.describe\([^\n]*=>\s*\{\s*\n")
_BEFORE_ALL_NEWPAGE_RE = re.compile(
    r"test\.beforeAll\(async\s*\(\s*\{\s*browser\s*\}\s*\)\s*=>\s*\{\s*\n"
    r"\s*page\s*=\s*await\s*browser\.newPage\(\);\s*\n"
)
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _translate_setup_step(step: Dict[str, Any]) -> str:
    """Translate one project.yaml setup step into a Playwright TS statement,
    mirroring tools/playwright_scanner.py._execute_setup_steps' action set."""
    if not isinstance(step, dict) or not step:
        return ""
    action = next(iter(step))
    if action == "goto":
        return f"    await page.goto({json.dumps(step['goto'])});"
    if action == "fill":
        spec = step.get("fill") or {}
        if not spec.get("selector"):
            return ""
        value_env = spec.get("value_env")
        if value_env:
            # Never embed the actual secret in generated source — emit a
            # reference resolved at test run time instead. Validate the name
            # is a safe bare identifier before interpolating it as raw TS.
            if not _ENV_VAR_NAME_RE.match(value_env):
                return ""
            return (
                f"    await page.locator({json.dumps(spec['selector'])})"
                f'.fill(process.env.{value_env} ?? "");'
            )
        return (
            f"    await page.locator({json.dumps(spec['selector'])})"
            f".fill({json.dumps(spec.get('value', ''))});"
        )
    if action == "click":
        return f"    await page.locator({json.dumps(step['click'])}).click();"
    if action == "wait":
        try:
            ms = int(step["wait"])
        except (KeyError, TypeError, ValueError):
            return ""
        return f"    await page.waitForTimeout({ms});"
    return ""  # unknown action — skip rather than emit broken TS


def _inject_setup_steps(spec_content: str, setup_steps: Optional[List[Dict[str, Any]]]) -> str:
    """Insert the module's setup sequence (e.g. login) so every test in this
    spec starts from the module's required state.

    Two shapes are supported:
      - Legacy/fallback-tier specs with a shared page (`test.beforeAll(async
        ({ browser }) => { page = await browser.newPage(); })`): setup runs
        ONCE, inserted right after that line.
      - Current action-library specs (per-test `{ action }` fixture, no
        shared page): falls back to inserting a
        `test.beforeEach(async ({ page }) => {...})` right after the
        `test.describe(...)` opening line — action-library specs don't
        destructure `page` themselves, but Playwright's own fixture always
        provides it, so a beforeEach hook can still use it directly.

    Returns spec_content unchanged if there are no usable setup steps, or if
    neither anchor can be found (never corrupt generated output)."""
    if not setup_steps:
        return spec_content

    lines = [line for line in (_translate_setup_step(s) for s in setup_steps) if line]
    if not lines:
        return spec_content

    before_all_match = _BEFORE_ALL_NEWPAGE_RE.search(spec_content)
    if before_all_match:
        insertion = "\n".join(lines) + "\n"
        idx = before_all_match.end()
        return spec_content[:idx] + insertion + spec_content[idx:]

    describe_match = _DESCRIBE_OPEN_RE.search(spec_content)
    if not describe_match:
        return spec_content

    hook = "\n  test.beforeEach(async ({ page }) => {\n" + "\n".join(lines) + "\n  });\n"
    idx = describe_match.end()
    return spec_content[:idx] + hook + spec_content[idx:]


def _load_suite(suite_path: str) -> dict:
    if not os.path.exists(suite_path):
        return {"specs": []}
    with open(suite_path, encoding="utf-8") as f:
        return json.load(f) or {"specs": []}


def _upsert_spec(suite: dict, spec_entry: dict) -> None:
    specs = suite.setdefault("specs", [])
    for i, s in enumerate(specs):
        if s.get("spec_id") == spec_entry["spec_id"]:
            specs[i] = spec_entry
            return
    specs.append(spec_entry)


def _write_suite(suite: dict, suite_path: str, project_name: str) -> None:
    suite["project"] = project_name
    suite["updated_at"] = datetime.now(timezone.utc).isoformat()
    suite["total_scenarios"] = len(suite.get("specs", []))
    suite["new_additions"] = [
        s["file"] for s in suite.get("specs", []) if s.get("status") == "new"
    ]
    with open(suite_path, "w", encoding="utf-8") as f:
        json.dump(suite, f, indent=2, ensure_ascii=False)


def _write_test_plans(test_plans: dict, test_plans_path: str) -> None:
    with open(test_plans_path, "w", encoding="utf-8") as f:
        json.dump(test_plans, f, indent=2, ensure_ascii=False)
