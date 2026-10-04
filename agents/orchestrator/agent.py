import os
import re
from datetime import datetime, timezone
from typing import Dict, Optional

import yaml

from agents.orchestrator.tools import build_final_report
from agents.registry import AgentRegistry
from connectors.connector_registry import ConnectorRegistry
from connectors.ns.base import NSCallError, NSHTTPConnector
from contracts.state_models import WorkflowState
from tools.shared import get_logger
from tools.state import project_state_manager as psm
from exceptions import AgentExecutionError

from tools.constants import PROJECTS_BASE as _PROJECTS_DIR
from tools.project_manifest import load_project_manifest, narrow_to_module


class OrchestratorAgent:
    def __init__(self, settings: dict, agents_config: dict, registry: AgentRegistry, run_id: str):
        self.settings = settings
        self.agents_config = agents_config
        self.registry = registry
        self.run_id = run_id
        self.state = WorkflowState(run_id=run_id, workflow_id="", workflow_name="")
        self.logger = get_logger("workflow")

        # NS connector is built lazily — only when a step is actually dispatched via NS
        self._ns_connector: NSHTTPConnector | None = None

        # Load NS registry — agent names that should be dispatched via HTTP
        ns_cfg = settings.get("execution", {}).get("ns", {})
        reg_path = ns_cfg.get("registry", "workflows/ns_registry.yaml")
        self._ns_registry: dict = {}
        if reg_path and os.path.exists(reg_path):
            with open(reg_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self._ns_registry = raw.get("agents", {})

        # Load agent registry — fallback chain specs per step
        agent_reg_path = ns_cfg.get("agent_registry", "workflows/agent_registry.yaml")
        self._agent_registry: dict = {}
        if agent_reg_path and os.path.exists(agent_reg_path):
            with open(agent_reg_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self._agent_registry = raw.get("agents", {})

        self._ns_call_trace: list = []

    def _is_agent_enabled(self, step_name: str) -> bool:
        agents = self.agents_config.get("agents", {})
        step_config = agents.get(step_name, {})
        return step_config.get("enabled", True)

    def _build_agent(self, step_name: str):
        return self.registry.build(step_name, settings=self.settings)

    def _load_project_manifest(self, project_name: str) -> dict:
        manifest_path = os.path.join(_PROJECTS_DIR, project_name, "project.yaml")
        if not os.path.exists(manifest_path):
            self.logger.info(f"No project manifest found at '{manifest_path}' — using request as-is")
            return {}
        flat = load_project_manifest(project_name)
        self.logger.info(
            f"Loaded project manifest for '{project_name}': url={flat.get('url')}, "
            f"brd_dir={flat.get('brd_dir')}, modules={len(flat.get('modules', []))}, "
            f"ns_base_url={flat.get('ns_base_url')}"
        )
        return flat

    def run(self, request: dict, workflow: object) -> dict:
        self.state.workflow_id = request.get("workflow", workflow.workflow_id)
        self.state.workflow_name = workflow.workflow_id

        project_name = request.get("project_name", "project")
        manifest = self._load_project_manifest(project_name)
        request = {**manifest, **request}

        # ── Narrow to a single module when --module flag is set ────────
        module_filter = request.get("module_filter")
        if module_filter and request.get("modules"):
            request = narrow_to_module(request, module_filter, project_name)
            self.logger.info(f"Module filter active — running only module '{module_filter}'")
            if request.get("url"):
                self.logger.info(f"Module '{module_filter}' overrides URL → {request['url']}")
            if request.get("setup_steps"):
                self.logger.info(f"Module '{module_filter}' has {len(request['setup_steps'])} setup step(s)")

        # ── Inject auth config based on strategy ───────────────────────
        auth = request.get("auth", {})
        strategy = auth.get("strategy", "storageState")
        storage_state_path = auth.get("storage_state_path", "")

        if auth.get("enabled") and strategy == "live_login":
            request["auth_config"] = auth
            self.logger.info("Auth strategy: live_login — login will execute before each scan and test run")
        elif storage_state_path and os.path.exists(storage_state_path):
            request["auth_storage_state"] = storage_state_path
            self.logger.info(f"Auth state active — '{storage_state_path}'")
        elif auth.get("enabled") and storage_state_path:
            self.logger.warning(
                f"Auth is enabled but '{storage_state_path}' not found — "
                "run: python main.py --project <name> --auth-setup"
            )

        # ── Load persistent project state ──────────────────────────────
        force_rediscover = request.get("force_rediscover", False)
        project_state = psm.load(project_name)
        request["project_state"] = project_state
        request["coverage_gaps"] = project_state.get("gaps", {})
        request["new_additions"] = psm.build_new_additions_suite(project_state)
        self.logger.info(
            f"Project state loaded — "
            f"{project_state['summary']['total_test_cases']} existing TCs, "
            f"{len(project_state['new_additions'])} in new_additions"
        )

        self.logger.info(f"Starting workflow {self.state.workflow_name} with run id {self.run_id}")

        # ── Mandatory LLM pre-flight — abort before any step runs if the LLM is
        # unreachable, rather than letting each step discover it independently and
        # potentially degrade to a fallback tier. test_execution_only has no LLM-calling
        # steps at all (just `npx playwright test` + report aggregation), so it's exempt.
        if workflow.workflow_id != "test_execution_only":
            health_check_failure = self._llm_health_check()
            if health_check_failure is not None:
                return health_check_failure

        upstream_failed = False
        brd_dir = request.get("brd_dir", "")

        for step in workflow.steps:
            if not self._is_agent_enabled(step):
                self.logger.info(f"Skipping disabled step {step}")
                continue

            if upstream_failed and step not in getattr(workflow, "always_run", set()):
                self.logger.warning(f"Skipping step '{step}' — upstream step failed")
                self.state.start_step(step)
                self.state.finish_step(step, status="skipped")
                continue

            # ── Discovery: skip if content unchanged (unless forced) ───
            if step == "discovery" and not force_rediscover:
                if not psm.discovery_needs_rerun(project_state, project_name, brd_dir, module_id=module_filter):
                    cached = project_state.get("discovery", {}).get("cached_output", {})
                    if cached:
                        self.logger.info(
                            "Discovery skipped — DOM and BRD fingerprints unchanged. "
                            "Use --force-rediscover to re-run."
                        )
                        self.state.start_step(step)
                        self.state.update_step(step, {**cached, "module": "discovery", "status": "skipped", "reason": "fingerprint_unchanged"})
                        self.state.finish_step(step, status="skipped")
                        continue

            self.logger.info(f"Starting step {step}")
            self.state.start_step(step)
            self.state.update_step(step, {"module": step, "response": "pending"})

            # ── Execution: target only new_additions suite ─────────────
            if step == "execution":
                force_execute = request.get("force_execute", False)
                suite = request.get("suite")
                new_suite_path = psm.write_new_additions_yaml(project_state, project_name)
                if new_suite_path:
                    request["target_suite"] = "new_additions"
                    request["suite_path"] = new_suite_path
                    self.logger.info(
                        f"Execution targeting new_additions suite ({len(project_state['new_additions'])} TCs)"
                    )
                elif suite:
                    self.logger.info(
                        f"Suite '{suite}' specified — running suite execution "
                        "(bypassing new_additions guard)"
                    )
                elif force_execute:
                    self.logger.info(
                        "force_execute=True — running all scripts found on disk "
                        "(project state has no new_additions)"
                    )
                else:
                    self.logger.info("No new additions to execute — skipping execution step")
                    self.state.update_step(step, {"module": "execution", "status": "skipped", "reason": "no_new_additions"})
                    self.state.finish_step(step, status="skipped")
                    continue

            try:
                result = self._try_with_fallbacks(step, request)

                self.state.update_step(step, result)
                step_status = result.get("status", "success") if isinstance(result, dict) else "success"
                self.state.finish_step(step, status=step_status)

                # ── Merge step output into project state ───────────────
                if step_status not in ("failed", "skipped"):
                    project_state = self._merge_step_into_state(
                        step, result, project_state, project_name, brd_dir, module_filter
                    )
                    request["project_state"] = project_state
                    # Persist after discovery so fingerprints survive a killed run.
                    # This prevents re-scanning an unchanged DOM on the next invocation.
                    if step == "discovery":
                        try:
                            psm.save(project_name, project_state)
                            self.logger.info(f"State checkpointed after step '{step}'")
                        except Exception as exc:
                            self.logger.warning(f"Checkpoint save failed after '{step}': {exc}")

                if step_status == "failed":
                    upstream_failed = True
                    reason = result.get("error", "agent returned status=failed")
                    self.state.record_error(step, reason)
                    self.logger.warning(f"Step {step} completed with status=failed: {reason}")
                    if isinstance(result, dict) and result.get("blocking"):
                        self.logger.error(
                            f"Blocking failure in step '{step}' — "
                            f"aborting remaining workflow steps. "
                            f"Fix this step before continuing."
                        )
                        break
                else:
                    self.logger.info(f"Step {step} completed with status={step_status}")
                    if step_status == "partial" and isinstance(result, dict):
                        reasons = result.get("partial_reasons") or (
                            [result["error"]] if result.get("error") else []
                        )
                        for reason in reasons:
                            self.logger.warning(f"  Step {step} partial — {reason}")

            except Exception as exc:
                upstream_failed = True
                reason = str(exc)
                self.state.record_error(step, reason)
                self.state.update_step(step, {"module": step, "error": reason})
                self.logger.error(f"Step {step} failed: {reason}")
                if isinstance(exc, AgentExecutionError):
                    continue
                continue

        # ── Persist updated project state ──────────────────────────────
        project_state = psm.graduate_additions(
            project_state, _resolve_execution_output(self.state.outputs)
        )
        project_state["last_run_id"] = self.run_id
        project_state["last_updated"] = datetime.now(timezone.utc).isoformat()
        try:
            psm.save(project_name, project_state)
            self.logger.info(f"Project state saved for '{project_name}'")
        except Exception as exc:
            self.logger.warning(f"Failed to save project state: {exc}")

        status = "failed" if self.state.errors else "success"
        final_report = build_final_report(
            run_id=self.state.run_id,
            workflow_name=self.state.workflow_name,
            status=status,
            steps_executed=self.state.completed_steps,
            outputs=self.state.outputs,
            execution_trace=self.state.execution_trace,
            errors=self.state.errors,
        )

        self.logger.info(f"Workflow {self.state.workflow_name} completed with status {status}")
        return {
            "state": self.state,
            "final_report": final_report,
            "ns_call_trace": self._ns_call_trace,
            "project_state": project_state,
        }

    def _llm_health_check(self) -> Optional[dict]:
        """
        One trivial LLM call before any workflow step runs — this is a hard go/no-go
        gate, not a normal step: no retry, no failure_classifier routing, no fallback
        tier. If the configured LLM connector can't even respond to "ping", every
        downstream step would either fail outright or silently degrade to a fallback
        (NS reroute / alt model / rule-based stub) — better to stop the whole run here,
        loudly, than spend minutes producing partial/degraded artifacts.

        Returns None if the LLM responded (proceed with the workflow), or an
        early-exit dict — same shape as run()'s normal return — if it didn't.
        """
        self.state.start_step("llm_health_check")
        try:
            llm = ConnectorRegistry(self.settings).get_llm()
            llm.generate("ping")
        except Exception as exc:
            reason = f"LLM pre-flight check failed: {type(exc).__name__}: {exc}"
            self.logger.error(reason)
            self.state.record_error("llm_health_check", reason)
            final_report = build_final_report(
                run_id=self.state.run_id,
                workflow_name=self.state.workflow_name,
                status="failed",
                steps_executed=[],
                outputs=self.state.outputs,
                execution_trace=self.state.execution_trace,
                errors=self.state.errors,
            )
            return {
                "state": self.state,
                "final_report": final_report,
                "ns_call_trace": self._ns_call_trace,
                "project_state": {},
            }

        self.logger.info("LLM pre-flight check passed")
        self.state.finish_step("llm_health_check", status="success")
        return None

    def _merge_step_into_state(
        self, step: str, result: dict, project_state: dict, project_name: str, brd_dir: str,
        module_id: str = None,
    ) -> dict:
        """Update project_state from the output of a completed step."""
        try:
            if step == "discovery":
                project_state = psm.merge_discovery(
                    project_state, project_name, result, brd_dir=brd_dir, module_id=module_id
                )

            elif step == "artifact_generator_testcases":
                # Read proposed TCs from disk (agent already wrote them)
                proposed = self._load_proposed_test_cases(project_name)
                if proposed:
                    # Run semantic dedup against existing TCs
                    existing_tcs = list(project_state.get("test_cases", {}).values())
                    approved = self._run_dedup(project_name, existing_tcs, proposed)
                    project_state = psm.merge_test_cases(project_state, proposed, approved)
                    self.logger.info(
                        f"Dedup result — {len(approved)}/{len(proposed)} proposed TCs approved"
                    )

            elif step == "script_generation":
                # Read specs written to test_suite.json — one TC per generated scenario.
                # No dedup pass here (script_generation doesn't propose duplicates the
                # way artifact_generator_testcases did), so every spec is both proposed
                # and approved; merge_test_cases already skips ids already in tc_map.
                generated = self._load_generated_test_cases(project_name)
                if generated:
                    project_state = psm.merge_test_cases(project_state, generated, generated)
                    self.logger.info(
                        f"script_generation — {len(generated)} test case(s) merged into project state"
                    )

            elif step in ("execution", "ui_execution"):
                project_state = psm.merge_run_results(
                    project_state, self.run_id, _with_test_case_ids(result)
                )

        except Exception as exc:
            self.logger.warning(f"State merge failed for step '{step}': {exc}")

        return project_state

    def _run_dedup(self, project_name: str, existing: list, proposed: list) -> list:
        """Call SemanticDedupAgent. Returns approved TC list (falls back to all proposed on error)."""
        try:
            from agents.test_creation.dedup.agent import SemanticDedupAgent
            agent = SemanticDedupAgent(settings=self.settings)
            dedup_request = {
                "existing_test_cases": existing,
                "proposed_test_cases": proposed,
                "connector_mode": self.settings.get("connectors", {}).get("llm"),
            }
            result = agent.execute(dedup_request, {})
            return result.get("approved", proposed)
        except Exception as exc:
            self.logger.warning(f"Dedup agent failed ({exc}) — all proposed TCs treated as approved")
            return proposed

    def _load_proposed_test_cases(self, project_name: str) -> list:
        """Read test_cases.yaml written by artifact_generator_testcases."""
        import yaml as _yaml
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in project_name).strip("_")
        path = os.path.join("application_assets", "projects", safe, "test_creation", "test_cases.yaml")
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                raw = _yaml.safe_load(f) or {}
            return raw.get("test_cases", [])
        except Exception:
            return []

    def _load_generated_test_cases(self, project_name: str) -> list:
        """Read test_suite.json written by script_generation and map each spec to
        the TC dict shape psm.merge_test_cases() expects. One TC per spec —
        spec_id (e.g. "BS-001") doubles as both test_case_id and business_scenario_id
        since script_generation writes one .spec.ts file per business scenario."""
        import json as _json
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in project_name).strip("_")
        path = os.path.join(_PROJECTS_DIR, safe, "test_creation", "test_suite.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                suite = _json.load(f) or {}
        except Exception:
            return []

        return [
            {
                "test_case_id": spec["spec_id"],
                "test_case_name": spec.get("scenario_title", spec["spec_id"]),
                "business_scenario_id": spec["spec_id"],
                "test_case_type": spec.get("module_id", "smoke"),
            }
            for spec in suite.get("specs", [])
            if spec.get("spec_id")
        ]

    def _ensure_ns_connector(self) -> NSHTTPConnector:
        if self._ns_connector is None:
            self._ns_connector = ConnectorRegistry(self.settings).get_ns()
            self.settings["ns_connector"] = self._ns_connector
            self.logger.info(
                f"NS connector initialised — {len(self._ns_registry)} agents registered: "
                f"{list(self._ns_registry.keys())}"
            )
        return self._ns_connector

    def _dispatch_ns(self, step: str, request: dict) -> dict:
        """Call the NS agent for this step and return a normalised result dict."""
        spec = self._ns_registry.get(step, {})
        method = spec.get("method", "POST").upper()
        endpoint = spec.get("endpoint", f"/{step}")
        ns_base_url = request.get("ns_base_url")
        effective_base = (ns_base_url or self.settings.get("execution", {}).get("ns", {}).get("base_url", "")).rstrip("/")
        full_url = effective_base + endpoint

        try:
            response = self._ensure_ns_connector().call(step, request, base_url=ns_base_url)
            if not isinstance(response, dict):
                response = {"response": response}
            response.setdefault("module", step)
            response.setdefault("status", "success")

            self._ns_call_trace.append({
                "step": step,
                "method": method,
                "url": full_url,
                "input": {k: v for k, v in request.items() if k != "ns_connector"},
                "response": response,
                "status": response.get("status", "success"),
                "error": None,
            })
            return response

        except KeyError:
            err = f"Agent '{step}' not found in NS registry"
            self._ns_call_trace.append({"step": step, "method": method, "url": full_url, "input": {}, "response": None, "status": "failed", "error": err})
            return {"module": step, "status": "failed", "error": err}
        except TimeoutError as exc:
            self._ns_call_trace.append({"step": step, "method": method, "url": full_url, "input": {}, "response": None, "status": "failed", "error": str(exc)})
            return {"module": step, "status": "failed", "error": str(exc)}
        except NSCallError as exc:
            self._ns_call_trace.append({"step": step, "method": method, "url": full_url, "input": {}, "response": None, "status": "failed", "error": str(exc)})
            return {"module": step, "status": "failed", "error": str(exc)}

    def _try_with_fallbacks(self, step: str, request: dict) -> dict:
        """Try the primary agent tier, then each fallback in order.

        Never raises — always returns a result dict.
        Routing is fully controlled by agent_registry.yaml:
          - connector_type: internal → try the internal Python agent first
          - connector_type: ns_http  → dispatch directly to NS (no internal agent attempt)
        Fallback tiers are listed under the step's fallbacks: key.
        """
        agent_spec = self._agent_registry.get(step, {})
        # Only entries explicitly marked enabled: true are ever tried — every
        # fallback tier ships disabled by default (see workflows/agent_registry.yaml).
        fallbacks = [fb for fb in agent_spec.get("fallbacks", []) if fb.get("enabled") is True]
        primary_ct = agent_spec.get("connector_type", "internal")

        if primary_ct != "internal":
            # NS-primary (or other non-internal) — skip internal agent entirely
            self.logger.info(f"Step '{step}' — primary tier: connector_type={primary_ct}")
            try:
                result = self._dispatch_fallback_tier(step, agent_spec, request)
                if result is not None and result.get("status") != "failed":
                    return result
                self.logger.warning(f"Step '{step}' primary tier returned failed — trying fallbacks")
            except Exception as exc:
                self.logger.warning(f"Step '{step}' primary tier raised {exc} — trying fallbacks")
        else:
            # Primary: internal Python agent
            try:
                agent = self._build_agent(step)
                result = agent.execute(request, self.state.__dict__)
                if result.get("status") != "failed":
                    return result
                self.logger.warning(f"Step '{step}' returned status=failed — trying fallbacks")
            except Exception as exc:
                self.logger.warning(
                    f"Step '{step}' raised {type(exc).__name__}: {exc} — trying fallbacks"
                )

        if not fallbacks:
            return {"module": step, "status": "failed", "error": f"step '{step}' failed and has no fallbacks configured", "blocking": False}

        # Fallback tiers: ns_http → python_stub (or any order defined in YAML)
        for i, fb in enumerate(fallbacks):
            ct = fb.get("connector_type")
            self.logger.info(f"Step '{step}' — fallback tier {i + 1}: connector_type={ct}")
            try:
                result = self._dispatch_fallback_tier(step, fb, request)
                if result is None:
                    continue  # tier not dispatchable here — already logged
                if result.get("status") != "failed":
                    return result
                self.logger.warning(f"Fallback tier {i + 1} ('{ct}') returned failed — trying next")
            except Exception as exc:
                self.logger.warning(f"Fallback tier {i + 1} ('{ct}') raised {exc} — trying next")

        return {"module": step, "status": "failed", "error": "all fallback tiers exhausted", "blocking": False}

    def _dispatch_fallback_tier(self, step: str, fb: dict, request: dict) -> Optional[dict]:
        """Dispatch one fallback tier based on its connector_type.

        Returns None (after logging a warning) for a tier the orchestrator cannot
        run as a whole-agent swap, so an enabled-but-undispatchable entry is
        skipped instead of crashing the cascade:
          - python_stub without fallback_module/fallback_class (those stubs are the
            agent's own per-call tier — agents/common/fallback_core.py)
          - alt_model / dom_synthesized / anything else (per-call tiers that only
            the agent itself can apply)
        """
        ct = fb.get("connector_type")
        if ct == "ns_http":
            agent_name = fb.get("agent_name", step)
            return self._dispatch_ns(agent_name, request)
        if ct == "python_stub":
            module_path = fb.get("fallback_module")
            class_name = fb.get("fallback_class")
            if not module_path or not class_name:
                self.logger.warning(
                    f"Step '{step}' — python_stub tier has no fallback_module/fallback_class; "
                    "it is applied per-call inside the agent, not as an orchestrator swap — skipping"
                )
                return None
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            agent = cls(settings=self.settings)
            result = agent.execute(request, self.state.__dict__)
            if isinstance(result, dict):
                result.setdefault("module", step)
            return result
        self.logger.warning(
            f"Step '{step}' — fallback connector_type '{ct}' is a per-call tier the agent "
            "applies itself; the orchestrator cannot dispatch it — skipping"
        )
        return None


# Matches both the legacy hyphenated scheme ("BS-001", "SC-001") and the
# current module-scoped scheme script_generation names specs with
# ("M03_BS_006").
_SPEC_ID_RE = re.compile(r"([A-Za-z]+\d+_BS_\d+|BS-\d+|SC-\d+)")


def _extract_test_case_id(spec_file: str) -> str:
    """Pull the spec id (e.g. "BS-001" or "M03_BS_006") out of a spec_file
    path like "M02/test_BS-007_search_for_products.spec.ts" or
    "M03/test_M03_BS_006_verify_page_title….spec.ts" — matches the naming
    convention script_generation uses (test_creation/test_suite.json spec_id)."""
    match = _SPEC_ID_RE.search(spec_file or "")
    return match.group(1) if match else ""


def _with_test_case_ids(result: dict) -> dict:
    """Return a copy of a ui_execution/execution result with test_case_id filled
    in on each entry (derived from spec_file), so psm.merge_run_results() can
    match results back to project_state's test_cases. Does not mutate the input."""
    results = result.get("results")
    if not results:
        return result

    annotated = [
        r if r.get("test_case_id") else {**r, "test_case_id": _extract_test_case_id(r.get("spec_file", ""))}
        for r in results
    ]
    return {**result, "results": annotated}


def _resolve_execution_output(outputs: dict) -> dict:
    """Return the ui_execution/execution step's output dict from workflow
    state.outputs. "ui_execution" is the current step name; "execution" is
    kept as a fallback for legacy workflow definitions — mirrors the same
    key resolution _merge_step_into_state uses for the per-step state merge,
    so graduate_additions() sees the same data rather than always {}."""
    return outputs.get("ui_execution") or outputs.get("execution", {})
