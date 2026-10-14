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
from contracts.artifacts import load_payload, load_records, save_artifact
from tools.base_url import resolve_project_base_url
from tools.safety.plan_filter import filter_plan
from tools.safety.policy import SafetyPolicy, load_safety_policy
from tools.state.review_queue import flag_missing_capability, flag_safety_drops, record_locator_drift
from agents.test_creation.script_generation.prompt import (
    ACTION_LIBRARY_PROMPT, DESIGN_CASES_PROMPT, LINT_FEEDBACK_BLOCK, LOCATOR_RECONCILE_PROMPT, ORACLE_PROMPT_BLOCK,
)
from tools.execution.config import load_execution_config
from tools.test_creation.script_generator.compose import (
    compose_spec, inject_setup_steps, module_role_for, translate_setup_step,
)
from agents.test_creation.script_generation.tools import (
    LOCATOR_FIRST_ACTIONS,
    LOCATOR_OR_NULL_ACTIONS,
    ORACLE_REQUIRED_FIELDS,
    RELOAD_AND_VERIFY,
    STORAGE_KINDS,
    STORAGE_RULES,
    VALUE_REQUIRED_ACTIONS,
    render_flows_module,
    render_spec_from_plan,
    update_catalog,
    write_named_locator_map,
    write_pages_module,
)
from tools.test_creation import assertion_linter
from connectors.connector_registry import ConnectorRegistry
from tools.config.agent_registry_config import fallback_enabled, python_stub_fallback_enabled
from tools.config.test_generation_config import DEFAULT_TEST_GENERATION_CONFIG, load_test_generation_config
from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.requirements.traceability import refresh_project as refresh_traceability
from tools.requirements.tracing import PlanTracer, record_drops
from tools.shared import get_logger
from tools.shared.llm_response_validator import parse_llm_json
from tools.test_design.config import design_enabled
from tools.test_design.store import cases_by_scenario, load_doc as load_design_doc

# Phase 3: design cases per LLM call. Small chunks keep the plan JSON short, so one bad step costs a retry of
# 6 cases, not of the whole scenario.
DESIGN_CHUNK_SIZE = 6

# Mirrors application_assets/_shared/runtime/ActionEngine.ts's public verbs,
# plus the "useFlow" pseudo-action (a call into flows.generated.ts instead of
# a raw ActionEngine method). Keep these two lists in sync by hand — there is
# no single source of truth across the Python/TypeScript boundary.
# Phase 4.6: "waitForTimeout" (a fixed sleep) is deliberately NOT here — ActionEngine keeps it only for
# human-authored flows.json, and _validate_plan rejects it in generated plans (FIXED_SLEEP_ACTIONS).
ALLOWED_ACTIONS = frozenset({
    "navigate", "click", "doubleClick", "hover", "enterText", "clearAndEnterText",
    "pressKey", "checkCheckbox", "uncheckCheckbox", "selectDropdownByText",
    "selectDropdownByValue", "scrollIntoView", "waitForElement",
    "dragAndDrop", "uploadFile", "verifyVisible", "verifyHidden", "verifyText",
    "verifyContainsText", "verifyValue", "verifyEnabled", "verifyDisabled",
    "verifyChecked", "verifyCount", "verifyUrl", "verifyUrlContains", "verifyTitle",
    "verifyTitleContains", "takeScreenshot", "goBack", "reload", "verifyNoPageErrors", "useFlow",
    # Phase 5 oracles (verifyNoNewConsoleErrors is renderer-appended, never planned)
    "verifyRequest", "verifyNoRequest", "verifyFieldInvalid", "verifyNoDialog", "verifyNotInjected",
    "verifyValidationMessage", "verifyAriaSnapshot", "rememberCount", "verifyCountChangedBy", "reloadAndVerify",
    "verifyDownload", "verifyNewTab", "verifyStorage", "verifyResponseSchema", "verifyApiState",
    # Phase 5 / 7.6 fault injection and time control
    "mockRoute", "setOffline", "setClock",
})

FIXED_SLEEP_ACTIONS = frozenset({"waitForTimeout"})


_UNKNOWN_BASE_URL_NOTE = (
    "(unknown — no URL is configured for this module; use \"navigate\" with no value "
    "and never invent an absolute URL)"
)


class ScriptGenerationAgent(BaseAgent):
    MODULE_NAME = "script_generation"

    def __init__(self, provider=None, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._registry = ConnectorRegistry(self.settings)
        self.logger = get_logger("agent.script_generation")
        # Phase 1: set per execute() when requirements.enabled + requirements.json exist; None = untraced.
        self._tracer: Optional[PlanTracer] = None
        self._oracles_on = False      # Phase 5: set per execute() from project.yaml `oracles.enabled`

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
        scenario_map = load_payload("scenario_element_map", sem_map_path, {}) or {}
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
        # Phase 4.5: execution.test_steps / module_roles (+ modules[].role, auth.roles) shape the rendered spec.
        render_opts = _render_options(safe, request)
        self._oracles_on = render_opts["oracles"]

        # Regenerate the Page-factory classes fresh every run — pure codegen
        # from locator_map.json, so it's always in sync with a human/HealingAgent
        # repair to the map, without a separate merge step of its own.
        write_pages_module(locator_map, pages_path, module_names=module_name_map)

        # Rebuild flows.generated.ts from flows.json every run — cheap,
        # deterministic, and keeps it in sync if a human edits flows.json.
        flows = _load_json_or_empty(flows_path)
        flows_meta = {name: f.get("params", []) for name, f in flows.items()}
        if flows:
            for flow_name, flow in flows.items():
                sleeps = [st for st in (flow.get("steps") or []) if isinstance(st, dict)
                          and st.get("action") in FIXED_SLEEP_ACTIONS]
                if sleeps:
                    self._log(f"flows.json flow '{flow_name}' uses waitForTimeout ({len(sleeps)}x) — a fixed sleep; "
                              "prefer waitForElement or a verify* step", level="warning")
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
            project_name, safe, locator_map, url, module_url_map, module_setup_map, locator_map_path
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

        # Phase 1 — requirements traceability (tc_id / ac_ids / tags); None when disabled.
        self._tracer = PlanTracer.for_project(safe, request, logger=self.logger)

        # Phase 3 — test design: with a profile, each scenario implements exactly the cases TestDesignAgent
        # selected for it (test_cases.json); a scenario with none selected gets no spec. None = legacy path.
        design_by_scenario: Optional[Dict[str, List[dict]]] = None
        if design_enabled(safe, request):
            design_doc = load_design_doc(project_dir)
            if design_doc is None:
                self._log("test_generation.profile is set but test_cases.json is missing — run the test_design "
                          "step first; generating with the legacy caps", level="warning")
            else:
                design_by_scenario = cases_by_scenario(design_doc)
                if self._tracer is not None:
                    self._tracer.set_design_cases(design_doc.get("test_cases") or [])
                stale = {sid: len(v) for sid, v in design_by_scenario.items() if sid in existing_spec_ids}
                if stale:
                    self._log(f"{sum(stale.values())} selected design case(s) belong to {len(stale)} scenario(s) "
                              f"that already have a spec ({', '.join(sorted(stale))}) and are NOT implemented — "
                              "delete those specs to regenerate them from test_cases.json", level="warning")

        if not uncovered:
            self._generate_nfr(safe)
            self._refresh_traceability(safe, request)
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
        test_plans = load_payload("test_plans", test_plans_path, {}) or {}
        safety_policy = (
            SafetyPolicy.from_request(request["safety"]) if isinstance(request.get("safety"), dict)
            else load_safety_policy(safe)
        )

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
            design_cases = None
            if design_by_scenario is not None:
                design_cases = design_by_scenario.get(sid) or []
                if not design_cases:
                    self._log(f"{sid}: no test cases selected for this scenario by test design "
                              "(profile/budget) — no spec generated")
                    continue
            self._log(f"Generating spec for {sid}: {title} [{module_id}]"
                      + (f" — {len(design_cases)} design case(s)" if design_cases else ""))

            elements = _get_elements_for_scenario(sid, scenario_map)
            test_data = test_data_map.get(sid, {})
            allowed_locators = _allowed_locator_entries_for_scenario(
                elements, reverse_locator_index, locator_map, unresolvable_keys,
                module_id=module_id,
            )
            if design_cases:
                allowed_locators = _with_design_locators(allowed_locators, design_cases, locator_map,
                                                         unresolvable_keys)

            effective_url = module_url_map.get(module_id, url)
            gen_config = load_test_generation_config(safe, module_id=module_id)

            # Use per-scenario fallback routing — a failure on one spec (whether
            # in generation, rendering, or writing) should not abort the rest,
            # so the whole per-scenario body is caught and recorded rather than
            # left to propagate out of the loop and fail the entire run.
            try:
                if design_cases:
                    kind, payload, tier_used, fallback_route = self._generate_design_spec(
                        request=request, scenario=scenario, allowed_locators=allowed_locators,
                        test_data=test_data, base_url=effective_url, gen_config=gen_config,
                        flows_meta=flows_meta, locator_map=locator_map, design_cases=design_cases,
                    )
                else:
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
                        if self._tracer is not None:
                            # keep missing_actions / missing_locators so traceability can say why its ACs are untested
                            test_plans[sid] = plan
                            _write_test_plans(test_plans, test_plans_path)
                        continue

                    # Phase 0 safety rails — the one choke point every plan tier
                    # passes through. Drops whole tests (never a lone step) and
                    # reports each drop; never silent.
                    plan, safety_dropped = filter_plan(plan, safety_policy, locator_map, flows)
                    if safety_dropped:
                        flag_safety_drops(
                            project_name, sid, safety_dropped, safety_policy.environment,
                            output_dir=project_dir,
                        )
                        for d in safety_dropped:
                            self._log(
                                f"{sid}: dropped test '{d.get('test')}' — {d.get('reason')} "
                                f"({d.get('rule')}: {d.get('detail')})",
                                level="warning",
                            )
                    if not plan.get("tests"):
                        self._log(f"{sid}: every test was dropped by the safety rails — skipping", level="warning")
                        warnings.append(f"{sid}: all tests dropped by safety rails (see human_review_queue.json)")
                        test_plans[sid] = plan
                        _write_test_plans(test_plans, test_plans_path)
                        continue

                    weak_names: List[str] = []
                    assertion_median = None
                    if render_opts["oracles"]:
                        plan, weak_names, assertion_median = self._lint_and_regenerate(
                            plan, request, scenario, allowed_locators, test_data, effective_url, flows_meta,
                            gen_config, locator_map, design_cases, allowed_keys={e["key"] for e in allowed_locators},
                        )

                    if self._tracer is not None:
                        plan = self._tracer.annotate(plan, scenario, module_id)
                        self._tracer.save()   # persist tc_id assignments with the plan that uses them
                    generation_mode = "action_library"
                    test_plans[sid] = plan

                module_setup = module_setup_map.get(module_id)
                role = module_role_for(
                    render_opts["module_roles"].get(module_id), render_opts["enabled"], render_opts["roles"],
                    render_opts["role_auth"], warn=lambda m: self._log(f"{sid}: {m}", level="warning"),
                ) if kind == "plan" else None
                spec_content = compose_spec(
                    plan if kind == "plan" else None, scenario, effective_url, spec_rel_path,
                    project=safe, flows_meta=flows_meta, module_setup=module_setup, role=role,
                    test_steps=render_opts["test_steps"], locator_map=locator_map,
                    oracles=render_opts["oracles"],
                    raw_content=None if kind == "plan" else payload,
                )
                if role:
                    self._log(f"{sid}: specs start as role '{role}' (test.use) — module setup steps not injected")
                elif module_setup:
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
                    **({"weak_oracle": weak_names} if weak_names else {}),
                    **({"assertion_score": assertion_median} if assertion_median is not None else {}),
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

        if self._tracer is not None:
            self._tracer.save()
        self._generate_nfr(safe)
        self._refresh_traceability(safe, request)

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

    # ── Phase 3: one plan built from the scenario's design cases, chunk by chunk ──

    def _generate_design_spec(self, request: dict, scenario: dict, allowed_locators: List[Dict[str, str]],
                              test_data: dict, base_url: str, flows_meta: Dict[str, List[str]],
                              gen_config: Optional[dict], locator_map: Optional[Dict[str, dict]],
                              design_cases: List[dict]):
        """Returns ("plan", plan, tier_used, None) like _generate_spec. Every chunk goes through the same tiers
        and guards; a chunk that fails is recorded as dropped (generation_failed) and the others still render.
        The merged plan holds at most one test per case — see _reconcile_design_plan."""
        sid = scenario.get("scenario_id", "")
        merged: Dict[str, Any] = {"tests": [], "missing_actions": [], "missing_locators": [], "dropped_tests": []}
        tier_used, failures, last_exc = 0, 0, None
        chunks = [design_cases[i:i + DESIGN_CHUNK_SIZE] for i in range(0, len(design_cases), DESIGN_CHUNK_SIZE)]
        for chunk in chunks:
            try:
                kind, payload, tier, _route = self._generate_spec(
                    request=request, scenario=scenario, allowed_locators=allowed_locators, test_data=test_data,
                    base_url=base_url, flows_meta=flows_meta, gen_config=gen_config, locator_map=locator_map,
                    design_cases=chunk,
                )
            except Exception as exc:
                failures += 1
                last_exc = exc
                self._log(f"{sid}: design chunk of {len(chunk)} case(s) failed: {exc}", level="warning")
                merged["dropped_tests"] += [{"test": c["title"], "case_id": c["id"], "reason": "generation_failed",
                                             "detail": str(exc)[:200]} for c in chunk]
                continue
            if kind != "plan":     # tier-2 raw stub spec cannot be merged into a plan
                merged["dropped_tests"] += [{"test": c["title"], "case_id": c["id"], "reason": "generation_failed",
                                             "detail": "only the python stub fallback produced output"} for c in chunk]
                continue
            tier_used = max(tier_used, tier)
            plan = _reconcile_design_plan(payload, chunk, oracles=self._oracles_on)
            merged["tests"] += plan["tests"]
            for key in ("missing_actions", "missing_locators", "dropped_tests"):
                merged[key] += [x for x in plan.get(key) or [] if x not in merged[key]]
        if failures == len(chunks) and last_exc is not None:
            raise last_exc
        return "plan", merged, tier_used, None

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
        design_cases: Optional[List[dict]] = None,
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
                    if self._tracer is not None:
                        plan = record_drops(plan, dropped, mismatched)
                    return "plan", plan, 1, None
                elif current_model is not None:
                    plan = self._plan_via_llm(
                        scenario, allowed_locators, test_data, base_url, flows_meta,
                        llm=self._alt_llm(current_model, request),
                        gen_config=gen_config,
                        locator_map=locator_map,
                        design_cases=design_cases,
                    )
                    return "plan", plan, 1, None
                else:
                    llm = self._registry.get_llm(request.get("connector_mode"))
                    plan = self._plan_via_llm(
                        scenario, allowed_locators, test_data, base_url, flows_meta,
                        llm=llm, gen_config=gen_config, locator_map=locator_map,
                        design_cases=design_cases,
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

    def _lint_and_regenerate(self, plan, request, scenario, allowed_locators, test_data, base_url, flows_meta,
                             gen_config, locator_map, design_cases, allowed_keys):
        """Phase 5.3: score every test; regenerate the weak ones ONCE with the linter feedback; whatever is still
        weak is marked "weak_oracle" (returned names -> test_suite.json). Returns (plan, weak_names, median)."""
        sid = scenario.get("scenario_id", "")
        report = assertion_linter.lint_plan(plan)
        if report["weak"]:
            self._log(f"{sid}: {len(report['weak'])} weak-oracle test(s) — regenerating once with linter feedback",
                      level="warning")
            try:
                weak_cases = [c for c in design_cases or []
                              if any(t.get("case_id") == c["id"] for t in plan["tests"]
                                     if t.get("name") in {w["name"] for w in report["weak"]})]
                retry = self._plan_via_llm(
                    scenario, allowed_locators, test_data, base_url, flows_meta,
                    llm=self._registry.get_llm(request.get("connector_mode")), gen_config=gen_config,
                    locator_map=locator_map, design_cases=weak_cases or design_cases,
                    lint_feedback=assertion_linter.feedback(report["weak"]),
                )
                if design_cases:
                    retry = _reconcile_design_plan(retry, weak_cases or design_cases, oracles=self._oracles_on)
                    weak_set = {w["name"] for w in report["weak"]}
                    merged = [t for t in plan["tests"] if t.get("name") not in weak_set] + retry["tests"]
                    candidate = {**plan, "tests": merged}
                else:
                    candidate = retry
                candidate_report = assertion_linter.lint_plan(candidate)
                if len(candidate_report["weak"]) < len(report["weak"]):
                    plan, report = candidate, candidate_report
            except Exception as exc:     # a failed regeneration keeps the original plan, flagged weak
                self._log(f"{sid}: lint regeneration failed ({type(exc).__name__}: {exc})", level="warning")
        weak_names = [w["name"] for w in report["weak"]]
        for t in plan["tests"]:
            if t.get("name") in weak_names:
                t["weak_oracle"] = True
        return plan, weak_names, report["median"]

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
        design_cases: Optional[List[dict]] = None,
        lint_feedback: str = "",
    ) -> dict:
        sid = scenario.get("scenario_id", "")
        gen_config = gen_config or dict(DEFAULT_TEST_GENERATION_CONFIG)

        flows_summary = {name: {"params": params} for name, params in flows_meta.items()}
        distinct_clusters = {e["cluster"] for e in allowed_locators if e.get("cluster")}
        cluster_count = len(distinct_clusters) or 1

        template = DESIGN_CASES_PROMPT if design_cases else ACTION_LIBRARY_PROMPT
        prompt = template.safe_substitute(
            design_cases_json=json.dumps([_design_case_view(c) for c in design_cases or []],
                                         ensure_ascii=False, indent=2),
            scenario_json=json.dumps(scenario, ensure_ascii=False, indent=2),
            test_data_json=json.dumps(test_data, ensure_ascii=False, indent=2),
            # No silent localhost fallback (Phase 0.6): an unknown base URL is said
            # so explicitly, and the plan then navigates with no value (= baseURL).
            base_url=base_url or _UNKNOWN_BASE_URL_NOTE,
            valid_actions_json=json.dumps(sorted(ALLOWED_ACTIONS), ensure_ascii=False, indent=2),
            valid_locators_json=json.dumps(allowed_locators, ensure_ascii=False, indent=2),
            valid_flows_json=json.dumps(flows_summary, ensure_ascii=False, indent=2),
            max_negative_cases=gen_config["max_negative_cases"],
            max_boundary_cases=gen_config["max_boundary_cases"],
            max_data_iterations=gen_config["max_data_iterations"],
            distinct_cluster_count=cluster_count,
            # Phase 1: the scenario's acceptance criteria (empty when untraced → prompt unchanged).
            acceptance_criteria_block=self._tracer.prompt_block(scenario) if self._tracer is not None else "",
            oracle_block=(ORACLE_PROMPT_BLOCK if self._oracles_on else "")
            + (LINT_FEEDBACK_BLOCK.substitute(feedback=lint_feedback) if lint_feedback else ""),
        )

        raw = llm.generate(prompt)
        plan = _parse_plan_json(raw, sid)
        allowed_keys = {e["key"] for e in allowed_locators}
        _validate_plan(plan, sid, ALLOWED_ACTIONS, allowed_keys, flows_meta)
        plan, dropped = _drop_placeholder_negative_tests(plan, test_data, design_cases)
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
        if self._tracer is not None:
            plan = record_drops(plan, dropped, mismatched)
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

    def _generate_nfr(self, safe: str) -> None:
        """Phase 7: the deterministic non-functional specs (project.yaml test_types), registered in test_suite.json and
        test_plans.json so they run with the suite and appear in traceability. A failure is logged, never fatal."""
        try:
            from pathlib import Path
            from tools.nonfunctional.generate import generate as nfr_generate, register as nfr_register
            pdir = Path(_ASSETS_BASE) / safe
            written = nfr_generate(pdir)
            counts = nfr_register(pdir, written)
            if written:
                self._log(f"Non-functional specs: {', '.join(f'{k} ({v})' for k, v in counts.items())}")
        except Exception as exc:
            self._log(f"Non-functional spec generation failed (non-fatal): {exc}", level="warning")

    def _refresh_traceability(self, safe: str, request: dict) -> None:
        """Phase 1.2: rebuild traceability.json after generation. A failure is logged, never fatal."""
        try:
            trace = refresh_traceability(safe, request)
        except Exception as exc:
            self._log(f"Traceability update failed (non-fatal): {exc}", level="warning")
            return
        if trace is not None:
            s = trace.summary
            self._log(f"Traceability: {s.get('acs_covered')}/{s.get('acs_automatable')} automatable AC(s) "
                      f"covered, {s.get('tests_unlinked')} unlinked test(s)")

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
        locator_map_path: str = "",
    ) -> set:
        """Once per project per run, grouped by module (one browser launch
        per module, not per scenario): verify every locator_map.json entry
        actually resolves on a live page. Returns the set of keys that
        failed — the caller excludes them from allowed_locators so the LLM
        is never offered a known-dead key — and reports them via
        record_locator_drift. A module whose page can't be reached at all
        is skipped entirely (never treated as "every key is dead").

        Phase 6.3: a key that resolves to exactly one element and has no `_fingerprint` yet gets one (role, name,
        label, container, position of that element) — the identity HealingAgent checks a future repair against."""
        # Grouped by (module, page): entries merged from form_model.json (Phase 3) carry the `_page_url` of the
        # crawled page they live on and are checked there, after the module's setup, not on the module page.
        # `_dynamic` entries (Phase 3: a form's error area, seen in form_model probes after a submit) do not exist on
        # page load, so a load-time check would always call them dead; they are not live-validated.
        by_module: Dict[Tuple[str, str], List[str]] = {}
        for key, entry in locator_map.items():
            if entry.get("_dynamic"):
                continue
            by_module.setdefault((entry.get("_module_id") or "_default", entry.get("_page_url") or ""), []).append(key)

        from tools.execution.config import load_execution_config
        test_id_attribute = load_execution_config(safe)["test_id_attribute"]

        from tools.healing.identity import live_fingerprint
        unresolvable: set = set()
        fingerprinted = 0
        for (module_id, page_url), keys in by_module.items():      # insertion order, as before Phase 3
            effective_url = page_url or module_url_map.get(module_id, url)
            scanner, page = self._get_validation_page(module_id, effective_url, module_setup_map)
            if page is None:
                continue
            dead_keys = []
            try:
                for key in keys:
                    try:
                        if not self._locator_entry_resolves(page, locator_map[key], test_id_attribute):
                            dead_keys.append(key)
                        elif locator_map_path and not locator_map[key].get("_fingerprint"):
                            fp = live_fingerprint(page, locator_map[key], test_id_attribute)
                            if fp:
                                locator_map[key]["_fingerprint"] = fp
                                fingerprinted += 1
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
        if fingerprinted and locator_map_path:
            try:
                with open(locator_map_path, encoding="utf-8") as f:
                    on_disk = json.load(f)
                for key, entry in locator_map.items():
                    if entry.get("_fingerprint") and key in on_disk and not on_disk[key].get("_fingerprint"):
                        on_disk[key]["_fingerprint"] = entry["_fingerprint"]
                with open(locator_map_path, "w", encoding="utf-8") as f:
                    json.dump(on_disk, f, indent=2)
                self._log(f"Recorded identity fingerprints for {fingerprinted} locator key(s) (Phase 6.3)")
            except (OSError, ValueError) as exc:
                self.logger.warning(f"Could not save locator fingerprints: {exc}")
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
    def _locator_entry_resolves(page, entry: dict, test_id_attribute: Optional[str] = None) -> bool:
        # Shared with HealingAgent (Phase 2): same count()==1 rule and the same fail-open on
        # unknown types / errors, plus the optional `frame` / `scope` entry fields. Phase 4: testid
        # entries use the project's execution.test_id_attribute, like the TS runtime.
        from tools.test_creation.script_generator.locator_resolve import entry_resolves
        return entry_resolves(page, entry, test_id_attribute)

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
    # v1 list, v2 envelope or a legacy id-map — contracts.artifacts handles all three.
    return {r.get("scenario_id", ""): r for r in load_records(path) if isinstance(r, dict) and r.get("scenario_id")}


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

def _reverse_locator_index(locator_map: dict) -> Dict[Any, str]:
    """Map each locator_map.json entry's _source_locator_id back to its key.

    Keyed by (module_id, source_id) — every module's scan numbers from LOC-0001,
    so a bare id is ambiguous across modules. A bare source_id key is also kept
    when it is unambiguous (single-module / flat projects, older callers)."""
    index: Dict[Any, str] = {}
    bare: Dict[str, set] = {}
    for key, entry in locator_map.items():
        sid = entry.get("_source_locator_id")
        if not sid:
            continue
        index[(entry.get("_module_id") or "_default", sid)] = key
        bare.setdefault(sid, set()).add(key)
    for sid, keys in bare.items():
        if len(keys) == 1:
            index[sid] = next(iter(keys))
    return index


def _allowed_locator_entries_for_scenario(
    elements: list,
    reverse_index: Dict[str, str],
    locator_map: dict,
    unresolvable_keys: Optional[set] = None,
    module_id: Optional[str] = None,
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
        key = (
            (reverse_index.get((module_id, loc_id)) if module_id else None)
            or reverse_index.get(("_default", loc_id))
            or reverse_index.get(loc_id)
        )
        if key and key not in seen and key not in unresolvable_keys:
            seen.add(key)
            entry = {"key": key, "description": locator_map.get(key, {}).get("description", "")}
            for field in ("action", "expected_result", "cluster", "confidence"):
                if el.get(field) is not None:
                    entry[field] = el[field]
            result.append(entry)
    return result


def _with_design_locators(allowed: List[Dict[str, Any]], design_cases: List[dict], locator_map: dict,
                          unresolvable_keys: Optional[set] = None) -> List[Dict[str, Any]]:
    """Phase 3: add the locator keys the scenario's design cases name (form fields on crawled pages, merged into
    locator_map.json by TestDesignAgent). Same rules as the semantic-map keys: must exist, never a dead key."""
    unresolvable_keys = unresolvable_keys or set()
    out = list(allowed)
    seen = {e["key"] for e in out}
    for case in design_cases:
        for key in (case.get("locator_keys") or {}).values():
            if key in seen or key not in locator_map or key in unresolvable_keys:
                continue
            seen.add(key)
            out.append({"key": key, "description": locator_map[key].get("description", "")})
    return out


def _design_case_view(case: dict) -> Dict[str, Any]:
    """What the plan prompt needs from a test case (no risk/budget bookkeeping)."""
    target = case.get("target") or {}
    view = {k: case.get(k) for k in ("id", "title", "test_type", "technique", "preconditions", "inputs",
                                     "steps_outline", "oracles", "locator_keys") if case.get(k)}
    if target.get("sample_url"):
        view["sample_url"] = target["sample_url"]
    return view


def _reconcile_design_plan(plan: dict, chunk: List[dict], oracles: bool = False) -> dict:
    """Keep exactly the tests that implement a case of this chunk (first one per case_id), force each test's
    type to the case's test_type, and record every case left unimplemented — never silent.
    oracles (project.yaml `oracles.enabled`): the case's oracles fill in what the plan left out (Phase 5.4)."""
    by_id = {c["id"]: c for c in chunk}
    tests, dropped, done = [], list(plan.get("dropped_tests") or []), set()
    for t in plan.get("tests") or []:
        cid = t.get("case_id")
        if cid not in by_id:
            dropped.append({"test": t.get("name", ""), "reason": "not_in_design",
                            "detail": f"case_id {cid!r} is not one of this chunk's cases"})
            continue
        if cid in done:
            dropped.append({"test": t.get("name", ""), "case_id": cid, "reason": "duplicate_case_test"})
            continue
        t = dict(t, type=by_id[cid]["test_type"])
        if oracles:
            t = _fill_placeholder_oracles(t, by_id[cid])
        problem = _design_test_problem(t, by_id[cid])
        if problem:
            # the guards inside _plan_via_llm saw the LLM's own "type"; the case's type is applied here, so the
            # same rules are re-applied now — a retyped test can never slip past them
            dropped.append({"test": t.get("name", ""), "case_id": cid, "reason": problem})
            continue
        if oracles:
            t = _append_case_oracles(t, by_id[cid])
        done.add(cid)
        tests.append(t)
    for cid, case in by_id.items():
        if cid in done:
            continue
        # a guard (placeholder negative / locator-type mismatch) may already have dropped it by name
        earlier = next((d for d in dropped if d.get("case_id") == cid or d.get("test") == case["title"]), None)
        if earlier is not None:
            earlier.setdefault("case_id", cid)
        else:
            dropped.append({"test": case["title"], "case_id": cid, "reason": "not_expressed"})
    out = dict(plan)
    out["tests"] = tests
    out["dropped_tests"] = dropped
    return out


# ── Phase 5.4: oracles come from test_cases.json, not from the LLM ──────────
#
# A design case carries the oracles Phase 3 derived from the BRD / observed probes. The LLM is asked to express
# them, but whatever it leaves out (or writes as an empty placeholder) is filled in here, deterministically:
#   error_text {contains}            -> an empty-string text assertion gets the case's message
#   field_invalid {field}            -> verifyFieldInvalid(<locator of field>)
#   no_request {method, url}         -> verifyNoRequest(method, <path of url>)
#   url_unchanged                    -> verifyUrlContains(<path the case starts on>)
# Expected-value precedence (plan 5.2): BRD > observed > code > LLM-inferred. A test whose case oracles are all
# LLM-inferred is marked `oracle_confidence: "low"` and reported, never presented as BRD-backed.

_REJECTION_ORACLES = frozenset({"error_text", "field_invalid", "no_request", "url_unchanged", "submission_rejected"})
_TEXT_ASSERTS = frozenset({"verifyText", "verifyContainsText"})


def _url_path(url: Any) -> Optional[str]:
    """Path part of an absolute or relative URL; None when absent or still a template (/orders/{id})."""
    if not url:
        return None
    from urllib.parse import urlparse
    path = urlparse(str(url)).path
    return path if path and "{" not in path else None


def _fill_placeholder_oracles(test: dict, case: dict) -> dict:
    """An empty-string text assertion is a placeholder: give it the case's expected message when there is one."""
    message = next((o.get("contains") for o in case.get("oracles") or []
                    if o.get("type") == "error_text" and o.get("contains")), None)
    if not message:
        return test
    steps = [dict(s, action="verifyContainsText", value=message)
             if isinstance(s, dict) and s.get("action") in _TEXT_ASSERTS and s.get("value") == "" else s
             for s in test.get("steps") or []]
    return dict(test, steps=steps)


def _append_case_oracles(test: dict, case: dict) -> dict:
    steps = list(test.get("steps") or [])
    flat = [s for s in steps if isinstance(s, dict)]
    flat += [x for s in flat if s.get("action") == "reloadAndVerify" for x in s.get("steps") or []]
    have = {s.get("action") for s in flat}
    keys = case.get("locator_keys") or {}
    target = case.get("target") or {}
    note = f"oracle from {case.get('id')}"
    added: List[dict] = []
    for o in case.get("oracles") or []:
        kind = o.get("type")
        if kind == "field_invalid":
            key = keys.get(o.get("field") or "")
            if key and not any(s.get("action") == "verifyFieldInvalid" and s.get("locator_key") == key for s in flat):
                added.append({"action": "verifyFieldInvalid", "locator_key": key, "message": note})
        elif kind == "no_request" and o.get("method") and "verifyNoRequest" not in have:
            path = _url_path(o.get("url")) or _url_path(target.get("sample_url")) or _url_path(target.get("url_template"))
            if path:
                added.append({"action": "verifyNoRequest", "method": str(o["method"]).upper(), "urlPattern": path,
                              "message": note})
        elif kind == "url_unchanged" and not have & {"verifyUrl", "verifyUrlContains"}:
            path = _url_path(target.get("sample_url")) or _url_path(target.get("url_template"))
            if path:
                added.append({"action": "verifyUrlContains", "value": path, "message": note})
    out = dict(test, steps=steps + added) if added else dict(test)
    sources = {str(o.get("source") or "") for o in case.get("oracles") or []}
    if sources and all("llm_inferred" in src for src in sources):
        out["oracle_confidence"] = "low"
    return out


def _case_has_rejection_basis(case: Optional[dict]) -> bool:
    return bool(case) and any(o.get("type") in _REJECTION_ORACLES for o in case.get("oracles") or [])


_FILL_ACTIONS = ("enterText", "clearAndEnterText", "selectDropdownByText", "selectDropdownByValue")


def _design_test_problem(test: dict, case: dict) -> Optional[str]:
    """Why a plan test does not really implement its design case (None = fine):
    no_assertion                 no verify* step at all — it would pass whatever the app does
    placeholder_negative_dropped a negative/boundary test whose every assertion expects "" (same rule as
                                 _drop_placeholder_negative_tests, applied after the case's type is forced)
    input_not_used               the value under test (e.g. the 51-character name) is never entered/uploaded"""
    steps = [s for s in test.get("steps") or [] if isinstance(s, dict)]
    verify = [s for s in steps if str(s.get("action", "")).startswith("verify")]
    if not verify:
        return "no_assertion"
    if test.get("type") in ("negative", "boundary") and all(s.get("value") == "" for s in verify):
        return "placeholder_negative_dropped"
    field = (case.get("target") or {}).get("field")
    spec = (case.get("inputs") or {}).get(field) if field else None
    value = spec.get("value") if isinstance(spec, dict) else None
    if isinstance(value, dict):
        if not any(s.get("action") == "uploadFile" for s in steps):
            return "input_not_used"
    elif isinstance(value, (str, int, float)) and str(value) != "":
        if not any(s.get("action") in _FILL_ACTIONS and str(s.get("value")) == str(value) for s in steps):
            return "input_not_used"
    return None


def _get_elements_for_scenario(sid: str, scenario_map: dict) -> List[Dict[str, Any]]:
    """Return relevant_elements list for a scenario, or [] if not in map."""
    entry = scenario_map.get(sid, {})
    return entry.get("relevant_elements", [])


def _render_options(safe_project: str, request: Optional[dict] = None) -> Dict[str, Any]:
    """execution.test_steps / module_roles / role_auth, modules[].role and the declared auth.roles names."""
    import yaml
    raw: dict = {}
    yaml_path = os.path.join(_ASSETS_BASE, safe_project, "project.yaml")
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception:
            raw = {}
    cfg = load_execution_config(safe_project)
    modules = (request or {}).get("modules") or raw.get("modules") or []
    roles = ((raw.get("auth") or {}).get("roles") or {}) if isinstance(raw.get("auth"), dict) else {}
    return {
        "test_steps": cfg["test_steps"],
        "oracles": bool((raw.get("oracles") or {}).get("enabled")) if isinstance(raw.get("oracles"), dict) else False,
        "enabled": cfg["module_roles"],
        "role_auth": cfg["role_auth"],
        "module_roles": {m["id"]: m.get("role") for m in modules if isinstance(m, dict) and m.get("id")},
        "roles": list(roles) if isinstance(roles, dict) else [],
    }


def _load_base_url(safe_project: str) -> str:
    """Resolve the project's base URL from project.yaml: `project.url`, else the
    single distinct `modules[].url` (several distinct module URLs -> "" — the caller
    uses the per-module URL instead). Never invents a default."""
    import yaml
    yaml_path = os.path.join(_ASSETS_BASE, safe_project, "project.yaml")
    if not os.path.exists(yaml_path):
        return ""
    try:
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return ""
    return resolve_project_base_url(cfg)


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

        remembered: set = set()
        for step in test["steps"]:
            _validate_step(step, scenario_id, allowed_actions, allowed_keys, allowed_flows, remembered)


def _validate_step(step, scenario_id: str, allowed_actions: frozenset, allowed_keys: set,
                   allowed_flows: Dict[str, List[str]], remembered: set, nested: bool = False) -> None:
    """One plan step (see _validate_plan). `remembered` collects rememberCount keys seen so far in the test, so a
    verifyCountChangedBy without an earlier baseline is rejected here instead of failing at run time."""
    from agents.common.failure_classifier import LLMResponseValidationError

    action = step.get("action") if isinstance(step, dict) else None
    if action in FIXED_SLEEP_ACTIONS:
        raise LLMResponseValidationError(
            f"{scenario_id}: step uses '{action}' — fixed sleeps are not allowed in generated plans; "
            "use waitForElement or a verify* step (they wait automatically)"
        )
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
        return

    if action == "dragAndDrop":
        for field in ("locator_key", "target_locator_key"):
            key = step.get(field)
            if key not in allowed_keys:
                raise LLMResponseValidationError(
                    f"{scenario_id}: dragAndDrop references disallowed locator_key '{key}'"
                )
        return

    if action == RELOAD_AND_VERIFY:
        inner = step.get("steps")
        if nested or not isinstance(inner, list) or not inner:
            raise LLMResponseValidationError(
                f"{scenario_id}: '{action}' needs a non-empty 'steps' list (and cannot be nested)")
        for sub in inner:
            if not str((sub or {}).get("action", "")).startswith("verify"):
                raise LLMResponseValidationError(
                    f"{scenario_id}: '{action}' may only contain verify* steps, got '{(sub or {}).get('action')}'")
            _validate_step(sub, scenario_id, allowed_actions, allowed_keys, allowed_flows, remembered, nested=True)
        return

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
    for field in ORACLE_REQUIRED_FIELDS.get(action, ()):
        if step.get(field) is None or step.get(field) == "":
            raise LLMResponseValidationError(
                f"{scenario_id}: step '{action}' is missing required '{field}' field"
            )
    if action in VALUE_REQUIRED_ACTIONS and step.get("value") is None:
        raise LLMResponseValidationError(
            f"{scenario_id}: step '{action}' is missing required 'value' field"
        )
    if action == "rememberCount":
        remembered.add(step.get("locator_key"))
    elif action == "verifyCountChangedBy":
        if step.get("locator_key") not in remembered:
            raise LLMResponseValidationError(
                f"{scenario_id}: verifyCountChangedBy on '{step.get('locator_key')}' needs an earlier rememberCount")
        if not isinstance(step.get("delta"), int) or isinstance(step.get("delta"), bool):
            raise LLMResponseValidationError(f"{scenario_id}: verifyCountChangedBy 'delta' must be an integer")
    elif action == "verifyStorage":
        if step.get("store") not in STORAGE_KINDS or step.get("rule") not in STORAGE_RULES:
            raise LLMResponseValidationError(
                f"{scenario_id}: verifyStorage needs store in {list(STORAGE_KINDS)} and rule in {list(STORAGE_RULES)}")
        if step["rule"] in ("equals", "contains") and step.get("value") is None:
            raise LLMResponseValidationError(f"{scenario_id}: verifyStorage rule '{step['rule']}' needs a 'value'")
    elif action == "verifyResponseSchema":
        if not isinstance(step.get("schema"), dict) and not step.get("schemaRef"):
            raise LLMResponseValidationError(f"{scenario_id}: verifyResponseSchema needs 'schema' (object) or 'schemaRef'")
    elif action == "verifyApiState" and not isinstance(step.get("expect"), dict):
        raise LLMResponseValidationError(f"{scenario_id}: verifyApiState 'expect' must be an object")


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
    plan: dict, test_data: dict, design_cases: Optional[List[dict]] = None,
) -> Tuple[dict, List[str]]:
    """Strip any "negative"-typed test whose only assertions are a hardcoded
    empty-string value, when this scenario's test_data has no real
    expected_error anywhere to justify one. Returns (possibly-updated plan,
    names of dropped tests).

    Phase 5.4: a test implementing a design case whose oracles say how the app rejects the input (error_text,
    field_invalid, no_request, ...) has a basis too — it is kept here, and _reconcile_design_plan replaces the
    placeholder with those oracles (or drops it there when they cannot be expressed)."""
    cases = {c.get("id"): c for c in design_cases or []}
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
            and not _case_has_rejection_basis(cases.get(test.get("case_id")))
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
# Moved to tools/test_creation/script_generator/compose.py (Phase 4.5) so rerender.py composes specs with the
# exact same code; the old names stay importable from here.
_translate_setup_step = translate_setup_step
_inject_setup_steps = inject_setup_steps


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
    save_artifact("test_suite", suite_path, suite)


def _write_test_plans(test_plans: dict, test_plans_path: str) -> None:
    save_artifact("test_plans", test_plans_path, test_plans)
