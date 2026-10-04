"""
DiscoveryAgent — mandatory gateway step for every workflow.

Rules (driven by inputs declared in application_assets/projects/{project}/project.yaml):

  BOTH (url + brd)
    ComprehensionAgent reads BRD and DOM scan run IN PARALLEL.
    Fallback: if BRD comprehension fails and DOM scan passed,
              rule-based Python synthesizer converts DOM intents directly
              → business_scenarios.json + business_scenarios.md (no LLM).
    Mandatory outputs — workflow BLOCKS if any are missing:
      test_creation/intents.yaml       (from DOM scan)
      test_comprehension/business_scenarios.json
      test_comprehension/business_scenarios.md

  URL ONLY (url, no brd)
    DOM scan runs first → intents.yaml written from scan output.
    Primary:  ComprehensionAgent reads synthetic BRD built from DOM intents
              → business_scenarios.json + business_scenarios.md.
    Fallback: if ComprehensionAgent fails (expired LLM credentials, network error),
              rule-based Python synthesizer converts DOM intents directly
              → business_scenarios.json + business_scenarios.md (no LLM).
    Mandatory outputs — workflow BLOCKS if any are missing:
      test_creation/intents.yaml       (from DOM scan)
      test_comprehension/business_scenarios.json
      test_comprehension/business_scenarios.md

  BRD ONLY (brd, no url)
    ComprehensionAgent reads BRD → business_scenarios.json + business_scenarios.md.
    No DOM scan; test execution steps are skipped (no locators available).
    Mandatory outputs — workflow BLOCKS if any are missing:
      test_comprehension/business_scenarios.json
      test_comprehension/business_scenarios.md
    Optional:
      test_creation/intents.yaml       (not generated — no URL)

  NONE (neither url nor brd)
    Fails immediately with status=failed, blocking=True.

All outputs written under application_assets/{project}/:
  test_creation/intents.yaml
  test_comprehension/business_scenarios.json
  test_comprehension/business_scenarios.md
  test_comprehension/dom_elements.json    (when URL present)
  test_comprehension/dom_intents.json     (when URL present)
  test_comprehension/synthetic_brd.md    (URL-only LLM path only — not written on fallback)
  test_comprehension/run_summary.json     (always — summary of what ran)
"""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

import yaml

from agents.base_agent import BaseAgent
from agents.comprehension.comprehension_agent.agent import ComprehensionAgent
from agents.comprehension.discovery.tools import (
    scan_dom,
    save_dom_scan,
    promote_checkpoint,
    comprehension_scan_dir,
    synthesize_brd_from_dom,
    synthesize_scenarios_from_dom,
    synthesize_scenarios_from_flows,
)
from tools.config.agent_registry_config import fallback_enabled
from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.shared import get_logger

# Mandatory outputs by mode — workflow is blocked if any are missing
_MANDATORY = {
    "both":     ["business_scenarios.json", "business_scenarios.md", "intents.yaml"],
    "url_only": ["business_scenarios.json", "business_scenarios.md", "intents.yaml"],
    "brd_only": ["business_scenarios.json", "business_scenarios.md"],
}


class DiscoveryAgent(BaseAgent):
    """
    Gateway discovery step.  Reads project.yaml inputs, runs the appropriate
    mode, verifies mandatory outputs, and blocks the workflow on failure.

    Request keys consumed:
        project_name     (str)  required
        url              (str)  optional — triggers DOM scan
        brd_dir          (str)  optional — triggers BRD comprehension
        browser          (str)  default chromium
        headless         (bool) default True
        application_name (str)  default project_name
    """

    # NOT used as an implicit default any more — _run_both() waits indefinitely
    # for both the comprehension and DOM-scan threads unless request["discovery_timeout_s"]
    # (populated from project.yaml's project.discovery_timeout_s — see
    # tools/project_manifest.py) is explicitly set. A BRD needs as long as it needs;
    # only opt into a bound if you have a specific reason to cap it. Kept around as a
    # documented reference value for projects that do want to set one, and because
    # Python cannot forcibly kill a wedged thread if a bound IS set and hit — that
    # case is a last-resort backstop, not a UX limit on interactive exploration
    # (tools/interactive_scanner.py's page "close"/"disconnected" handlers are the
    # real, near-instant stop signal there).
    _DISCOVERY_PARALLEL_TIMEOUT_S = 60

    def __init__(self, settings: Optional[Dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.discovery")

    # ──────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)

        has_url = bool(request.get("url", "").strip())
        has_brd = self._brd_exists(request)

        self.logger.info(
            f"DiscoveryAgent — project='{project_name}' "
            f"has_url={has_url} has_brd={has_brd}"
        )

        if has_url and has_brd:
            mode = "both"
            result = self._run_both(request, state, safe)
        elif has_brd:
            mode = "brd_only"
            result = self._run_brd_only(request, state, safe)
        elif has_url:
            mode = "url_only"
            result = self._run_url_only(request, state, safe)
        else:
            self.logger.error("DiscoveryAgent: neither URL nor BRD provided — no valid input")
            return {
                "module": "discovery",
                "mode": "none",
                "status": "failed",
                "blocking": True,
                "error": (
                    "No valid input found in project.yaml. "
                    "Provide 'url', 'brd_dir', or both. "
                    "Workflow cannot continue."
                ),
            }

        result["mode"] = mode
        result["module"] = "discovery"

        module_id = request.get("module_filter")
        interactive = bool(request.get("interactive_scan", False))

        # ── Mandatory output gate ───────────────────────────────────────
        missing = self._check_mandatory_outputs(mode, safe, module_id, interactive)
        if missing:
            msg = (
                f"Discovery mandatory outputs missing: {', '.join(missing)}. "
                f"Downstream workflow is blocked until these files are produced. "
                f"Fix the discovery step (check LLM credentials, URL reachability, "
                f"or BRD file path) and re-run."
            )
            self.logger.error(msg)
            result["status"] = "failed"
            result["error"] = msg
            result["blocking"] = True
            result["missing_outputs"] = missing

        self._write_run_summary(result, safe, module_id)

        self.logger.info(
            f"DiscoveryAgent done — mode={mode} status={result.get('status')} "
            f"scenarios={result.get('scenarios_count', 0)} "
            f"dom_intents={result.get('dom_intents_count', 0)}"
        )
        return result

    # ──────────────────────────────────────────────────────────────────
    # Three modes
    # ──────────────────────────────────────────────────────────────────

    def _run_both(self, request: dict, state: dict, safe: str) -> Dict[str, Any]:
        """
        BOTH mode — parallel execution.

          [parallel] DOM scan → dom_intents.json → test_creation/intents.yaml
          [parallel] ComprehensionAgent reads BRD → business_scenarios.json + .md
          Fallback: if BRD comprehension fails, ComprehensionAgent reads
                    synthetic BRD built from DOM scan output.
        """
        self.logger.info(
            "Discovery mode: BOTH\n"
            "  [parallel] DOM scan → dom_intents.json → test_creation/intents.yaml\n"
            "  [parallel] ComprehensionAgent reads BRD → business_scenarios.json + .md\n"
            "  Fallback: BRD fails → ComprehensionAgent reads synthetic BRD from DOM"
        )

        comp_result: Dict = {}
        scan_result: Dict = {}
        errors: List[str] = []

        # Snapshot business_scenarios.json's mtime (or its absence) before
        # comprehension runs, so that if it times out we can tell whether the
        # per-module incremental export (see ComprehensionAgent._execute_modular)
        # actually wrote something fresh during THIS run, vs. the file just
        # being stale leftovers from a previous run.
        comp_dir_snapshot = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        bs_json_snapshot = os.path.join(comp_dir_snapshot, "business_scenarios.json")
        bs_mtime_before = (
            os.path.getmtime(bs_json_snapshot) if os.path.exists(bs_json_snapshot) else None
        )

        def _run_comp() -> None:
            nonlocal comp_result
            try:
                comp_result = self._run_comprehension(request, state)
            except Exception as exc:
                errors.append(str(exc))
                self.logger.error(f"Discovery parallel task raised: {exc}")

        def _run_scan() -> None:
            nonlocal scan_result
            try:
                scan_result = self._run_dom_scan(request, safe)
            except Exception as exc:
                errors.append(str(exc))
                self.logger.error(f"Discovery parallel task raised: {exc}")

        # Plain daemon threads, not ThreadPoolExecutor: a wedged DOM scan
        # (e.g. an interactive session whose Playwright connection hangs
        # after the browser is closed) must never block process exit.
        # ThreadPoolExecutor registers every worker thread in a global
        # atexit hook that unconditionally joins it on interpreter shutdown
        # regardless of how the pool itself is closed — daemon threads carry
        # no such hook and are simply abandoned when the process exits.
        t_comp = threading.Thread(target=_run_comp, name="discovery-comprehension", daemon=True)
        t_scan = threading.Thread(target=_run_scan, name="discovery-dom-scan", daemon=True)
        # No default here on purpose: comprehension/discovery should take as long as the
        # BRD genuinely needs unless a project explicitly opts into a bound via
        # project.yaml's project.discovery_timeout_s (see project_manifest.py). Passing
        # timeout=None to Thread.join() blocks until the thread actually finishes, so
        # t_comp/t_scan.is_alive() below is only ever True when a bound was set and hit.
        timeout_s = request.get("discovery_timeout_s")
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        t_comp.start()
        t_scan.start()
        t_comp.join(timeout=None if deadline is None else max(0.0, deadline - time.monotonic()))
        t_scan.join(timeout=None if deadline is None else max(0.0, deadline - time.monotonic()))

        if t_comp.is_alive():
            promoted = self._promote_comprehension_partial(safe, bs_mtime_before)
            if promoted:
                self.logger.warning(
                    f"Discovery: comprehension did not finish within {timeout_s}s — abandoning "
                    f"it, but {promoted['scenarios_count']} scenario(s) it already wrote to disk "
                    "before the deadline are being kept. The background thread is a daemon and "
                    "will be dropped on process exit, not killed."
                )
                errors.append(
                    f"comprehension timed out after {timeout_s}s — kept "
                    f"{promoted['scenarios_count']} scenario(s) written before the deadline"
                )
                comp_result = {"comprehension_status": "partial", **promoted}
            else:
                self.logger.error(
                    f"Discovery: comprehension did not finish within {timeout_s}s — "
                    "abandoning it so the pipeline doesn't hang. No scenarios had been "
                    "written before the deadline. The background thread is a daemon and "
                    "will be dropped on process exit, not killed."
                )
                errors.append(f"comprehension timed out after {timeout_s}s")
                comp_result = {"comprehension_status": "failed", "comprehension_error": f"timed out after {timeout_s}s"}
        if t_scan.is_alive():
            checkpoint_path = self._dom_checkpoint_path(request, safe)
            promoted = self._promote_dom_checkpoint(checkpoint_path, request, safe)
            if promoted:
                self.logger.warning(
                    f"Discovery: DOM scan did not finish within {timeout_s}s — abandoning it, "
                    f"but {promoted['dom_intents_count']} intent(s) captured before the deadline "
                    "are being kept. The scan may still be running in the background and will "
                    "overwrite these with the full result if it eventually completes."
                )
                errors.append(
                    f"DOM scan timed out after {timeout_s}s — kept "
                    f"{promoted['dom_intents_count']} intent(s) captured before the deadline"
                )
                scan_result = promoted
            else:
                self.logger.error(
                    f"Discovery: DOM scan did not finish within {timeout_s}s — abandoning it "
                    "so the pipeline doesn't hang. This usually means the interactive-scan "
                    "browser session wedged after closing (a known Playwright edge case); "
                    "no elements had been captured before the deadline, so the pipeline will "
                    "proceed without DOM data for this run. The background thread is a daemon "
                    "and will be dropped on process exit, not killed."
                )
                errors.append(f"DOM scan timed out after {timeout_s}s")
                scan_result = {"dom_status": "failed", "error": f"timed out after {timeout_s}s"}

        comp_failed = comp_result.get("comprehension_status") == "failed"
        scan_failed = scan_result.get("dom_status") == "failed"

        # Save DOM intents as intents.yaml (mandatory for BOTH mode)
        intents_path = ""
        if not scan_failed:
            intents_path = self._save_intents_yaml(
                dom_intents=scan_result.get("dom_intents_raw", []),
                safe=safe,
                project_name=request.get("project_name", safe),
                source="ui_scanner",
                module_id=request.get("module_filter"),
            )
            self.logger.info(f"  intents.yaml written → '{intents_path}'")

        # Flow-based scenarios from interactive scan (confidence=0.95, always run if flows exist)
        user_flows = scan_result.get("user_flows", [])
        if user_flows and not scan_failed:
            comp_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
            try:
                self.logger.info(
                    f"  Synthesizing {len(user_flows)} flow-based scenario(s) (confidence=0.95)"
                )
                synthesize_scenarios_from_flows(
                    user_flows=user_flows,
                    project_name=request.get("project_name", safe),
                    application_name=request.get("application_name", safe),
                    output_dir=comp_dir,
                )
            except Exception as flow_exc:
                self.logger.warning(f"  Flow scenario synthesis failed: {flow_exc}")

        # Fallback: BRD comprehension failed but DOM scan passed →
        # use rule-based Python synthesizer (no LLM required)
        if comp_failed and not scan_failed:
            dom_intents = scan_result.get("dom_intents_raw", [])
            if dom_intents and not fallback_enabled("discovery", "dom_synthesized", self.settings):
                self.logger.error(
                    "  BRD comprehension failed and discovery's 'dom_synthesized' fallback "
                    "tier is disabled in workflows/agent_registry.yaml — not degrading to "
                    "generic DOM-click scenarios"
                )
            elif dom_intents:
                self.logger.warning(
                    "  BRD comprehension failed — falling back to DOM-based "
                    "scenario synthesis (no LLM)"
                )
                comp_result = self._run_synthetic_comprehension(
                    dom_intents=dom_intents,
                    request=request,
                    safe=safe,
                )
                comp_failed = comp_result.get("comprehension_status") == "failed"
                if comp_failed:
                    self.logger.error(
                        f"  Synthetic scenario generation also failed — "
                        f"{comp_result.get('comprehension_error', 'unknown')}."
                    )

        # ComprehensionAgent can itself report "partial" (some modules skipped)
        # without ever hitting the outer timeout — surface that reason too.
        if comp_result.get("comprehension_status") == "partial" and comp_result.get("comprehension_error"):
            errors.append(f"comprehension: {comp_result['comprehension_error']}")

        if comp_failed and scan_failed:
            status = "failed"
        elif comp_failed or scan_failed or errors:
            status = "partial"
        else:
            status = "success"

        return {
            "status": status,
            "intents_path": intents_path,
            "partial_reasons": errors,
            **_merge(comp_result, scan_result),
        }

    def _dom_checkpoint_path(self, request: dict, safe: str) -> str:
        module_id = request.get("module_filter")
        comp_root = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        comp_dir = comprehension_scan_dir(comp_root, module_id)
        return os.path.join(comp_dir, ".dom_scan_checkpoint.json")

    def _promote_dom_checkpoint(
        self, checkpoint_path: str, request: dict, safe: str
    ) -> Optional[Dict[str, Any]]:
        """
        Turn whatever elements the abandoned DOM-scan thread had already
        collected into real dom_elements.json/dom_intents.json artifacts,
        via the same save_dom_scan() write path a completed scan uses — so
        a timed-out scan still leaves usable, real locators instead of
        nothing. Returns None if there's no checkpoint or it captured zero
        elements.
        """
        if not os.path.exists(checkpoint_path):
            return None
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                ckpt = json.load(f)
        except Exception as exc:
            self.logger.warning(f"  DOM checkpoint unreadable: {exc}")
            return None

        elements = ckpt.get("elements") or []
        if not elements:
            return None

        module_id = request.get("module_filter")
        project_name = request.get("project_name", safe)
        comp_root = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        comp_dir = comprehension_scan_dir(comp_root, module_id)

        paths = save_dom_scan(
            scan_data={"elements": elements, "element_count": len(elements)},
            url=ckpt.get("url", request.get("url", "")),
            project_name=project_name,
            output_dir=comp_dir,
            module_id=module_id,
        )
        dom_intents_raw = _load_dom_intents_raw(paths["dom_intents"])
        return {
            "dom_status": "partial",
            "dom_intents_count": len(dom_intents_raw),
            "dom_intents_path": paths["dom_intents"],
            "dom_elements_path": paths["dom_elements"],
            "dom_intents_raw": dom_intents_raw,
        }

    def _promote_comprehension_partial(
        self, safe: str, bs_mtime_before: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        """
        Check whether ComprehensionAgent's per-module incremental export
        (see ComprehensionAgent._execute_modular) wrote fresh scenario data
        to business_scenarios.json DURING this run before the timeout fired.
        Compares mtime against the pre-run snapshot so stale leftovers from
        a previous run aren't mistaken for this run's partial progress.
        """
        comp_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        bs_json_path = os.path.join(comp_dir, "business_scenarios.json")
        if not os.path.exists(bs_json_path):
            return None
        mtime_after = os.path.getmtime(bs_json_path)
        if bs_mtime_before is not None and mtime_after <= bs_mtime_before:
            return None
        try:
            with open(bs_json_path, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return None
        scenarios_count = payload.get("total_scenarios", len(payload.get("scenarios", [])))
        if not scenarios_count:
            return None
        return {
            "comprehension_source": "partial_checkpoint",
            "scenarios_count": scenarios_count,
            "business_scenarios_path": bs_json_path,
        }

    def _run_url_only(self, request: dict, state: dict, safe: str) -> Dict[str, Any]:
        """
        URL ONLY mode — sequential.

          Step 1  DOM scan → dom_intents.json + test_creation/intents.yaml (no LLM)
          Step 2  (primary)  Synthesize BRD → ComprehensionAgent (LLM)
                             → business_scenarios.json + .md
          Step 2' (fallback) If LLM unavailable: rule-based Python synthesizer
                             → business_scenarios.json + .md (no LLM)
        """
        self.logger.info(
            "Discovery mode: URL ONLY\n"
            "  [step 1] DOM scan → dom_intents.json + test_creation/intents.yaml (no LLM)\n"
            "  [step 2] ComprehensionAgent (LLM) → business_scenarios.json + .md\n"
            "  [fallback] If LLM unavailable → Python synthesizer (no LLM)"
        )

        # Step 1: DOM scan
        scan_result = self._run_dom_scan(request, safe)
        if scan_result.get("dom_status") == "failed":
            return {
                "status": "failed",
                "error": scan_result.get("error", "DOM scan failed"),
            }

        dom_intents = scan_result.get("dom_intents_raw", [])
        self.logger.info(f"  [1/2] DOM scan done — {len(dom_intents)} intents extracted")

        # Save DOM intents as intents.yaml immediately
        intents_path = self._save_intents_yaml(
            dom_intents=dom_intents,
            safe=safe,
            project_name=request.get("project_name", safe),
            source="ui_scanner",
            module_id=request.get("module_filter"),
        )
        self.logger.info(f"  [1/2] intents.yaml written → '{intents_path}'")

        # Step 2 (primary): Synthesize BRD → ComprehensionAgent (LLM)
        comp_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        user_flows = scan_result.get("user_flows", [])

        # Flow-based scenarios (confidence=0.95, no LLM) — run first, always
        if user_flows:
            try:
                self.logger.info(
                    f"  Synthesizing {len(user_flows)} flow-based scenario(s) (confidence=0.95)"
                )
                synthesize_scenarios_from_flows(
                    user_flows=user_flows,
                    project_name=request.get("project_name", safe),
                    application_name=request.get("application_name", safe),
                    output_dir=comp_dir,
                )
            except Exception as flow_exc:
                self.logger.warning(f"  Flow scenario synthesis failed: {flow_exc}")

        synthetic_path = synthesize_brd_from_dom(
            dom_intents=dom_intents,
            url=request.get("url", ""),
            application_name=request.get("application_name", safe),
            output_dir=comp_dir,
            user_flows=user_flows if user_flows else None,
        )
        synth_request = {**request, "brd_dir": synthetic_path}
        self.logger.info("  [2/2] ComprehensionAgent (LLM) processing synthetic BRD")
        comp_result = self._run_comprehension(synth_request, state)

        # Step 2' (fallback): LLM failed — use rule-based Python synthesizer
        if comp_result.get("comprehension_status") == "failed":
            if not fallback_enabled("discovery", "dom_synthesized", self.settings):
                self.logger.error(
                    "  [2/2] ComprehensionAgent failed and discovery's 'dom_synthesized' "
                    "fallback tier is disabled in workflows/agent_registry.yaml — not "
                    "degrading to generic DOM-click scenarios"
                )
            else:
                self.logger.warning(
                    "  [2/2] ComprehensionAgent failed "
                    f"({comp_result.get('comprehension_error', 'unknown')}) — "
                    "falling back to DOM-based scenario synthesis (no LLM)"
                )
                comp_result = self._run_synthetic_comprehension(
                    dom_intents=dom_intents,
                    request=request,
                    safe=safe,
                )
        else:
            comp_result["comprehension_source"] = "ui_scanner"

        self.logger.info(
            f"  [2/2] Scenarios done — "
            f"{comp_result.get('scenarios_count', 0)} scenario(s) "
            f"(source: {comp_result.get('comprehension_source', 'llm')})"
        )

        comp_status = comp_result.get("comprehension_status")
        if comp_status == "failed":
            overall_status = "failed"
        elif comp_status == "partial":
            overall_status = "partial"
        else:
            overall_status = "success"
        return {
            "status": overall_status,
            "intents_path": intents_path,
            **_merge(comp_result, scan_result),
        }

    def _run_brd_only(self, request: dict, state: dict, safe: str) -> Dict[str, Any]:
        """
        BRD ONLY mode.

          ComprehensionAgent reads BRD → business_scenarios.json + .md.
          No DOM scan; no intents.yaml (optional for this mode).
          Test execution steps downstream will be skipped (no locators).
        """
        self.logger.info(
            "Discovery mode: BRD ONLY\n"
            "  ComprehensionAgent reads BRD → business_scenarios.json + .md\n"
            "  Note: test execution steps will be skipped (no URL → no locators)"
        )
        comp_result = self._run_comprehension(request, state)
        comp_status = comp_result.get("comprehension_status")
        if comp_status == "failed":
            status = "failed"
        elif comp_status == "partial":
            status = "partial"
        else:
            status = "success"
        return {"status": status, **_merge(comp_result, {})}

    # ──────────────────────────────────────────────────────────────────
    # Sub-tasks
    # ──────────────────────────────────────────────────────────────────

    def _run_comprehension(self, request: dict, state: dict) -> Dict[str, Any]:
        # Primary: local LLM agent
        local_error: Optional[Exception] = None
        try:
            agent = ComprehensionAgent(settings=self.settings)
            result = agent.execute(request, state)
            out = {
                "comprehension_status": result.get("status"),
                "scenarios_count": result.get("scenarios_valid", 0),
                "business_scenarios_path": (result.get("output") or {}).get("json", ""),
            }
            if result.get("status") == "partial":
                out["comprehension_error"] = result.get("error", "some modules were skipped")
            return out
        except Exception as exc:
            local_error = exc
            self.logger.warning(f"ComprehensionAgent raised: {exc} — trying NS fallback")

        # NS fallback tier: try NeuroStack comprehension_agent before DOM synthesis
        if not fallback_enabled("discovery", "ns_http", self.settings):
            self.logger.warning(
                "discovery's 'ns_http' fallback tier is disabled in "
                "workflows/agent_registry.yaml — not rerouting to NeuroStack"
            )
            return {"comprehension_status": "failed", "comprehension_error": str(local_error)}

        ns_connector = self.settings.get("ns_connector")
        ns_base_url = request.get("ns_base_url")
        if ns_connector is not None:
            try:
                ns_result = ns_connector.call("comprehension_agent", request, base_url=ns_base_url)
                self.logger.info(f"NS comprehension_agent raw response: {ns_result}")
                if isinstance(ns_result, dict) and ns_result.get("status") != "failed":
                    self.logger.info(
                        f"NS comprehension_agent accepted — "
                        f"scenarios={ns_result.get('scenarios_count', ns_result.get('scenarios_valid', 0))} "
                        f"path='{ns_result.get('business_scenarios_path', '')}'"
                    )
                    return {
                        "comprehension_status": ns_result.get("status", "success"),
                        "scenarios_count": ns_result.get("scenarios_valid", ns_result.get("scenarios_count", 0)),
                        "business_scenarios_path": ns_result.get("business_scenarios_path", ""),
                    }
                self.logger.warning(f"NS comprehension_agent returned status=failed — trying DOM synthesis")
            except Exception as ns_exc:
                self.logger.warning(f"NS comprehension_agent raised: {ns_exc} — trying DOM synthesis")

        return {"comprehension_status": "failed", "comprehension_error": str(local_error)}

    def _run_dom_scan(self, request: dict, safe: str) -> Dict[str, Any]:
        url = request.get("url", "")
        browser = request.get("browser", "chromium")
        headless = request.get("headless", True)
        project_name = request.get("project_name", safe)
        interactive = request.get("interactive_scan", False)
        module_id = request.get("module_filter")
        comp_root = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        comp_dir = comprehension_scan_dir(comp_root, module_id)

        # Auth/setup are resolved the same way regardless of interactive_scan —
        # a module's login sequence must run whether the DOM scan is interactive
        # or headless. Only the scan mechanism itself should depend on the flag.
        storage_state_path = request.get("auth_storage_state")
        auth_cfg = request.get("auth", {})
        live_auth = auth_cfg if auth_cfg.get("strategy") == "live_login" else None
        setup_steps = request.get("setup_steps")

        try:
            if interactive:
                return self._read_recorded_scan(comp_dir, comp_root, url, project_name, module_id)

            self.logger.info(f"DOM scan starting: {url}")
            if setup_steps:
                self.logger.info(f"  {len(setup_steps)} setup step(s) will run before scan")
            # comp_dir must exist before the scan starts — the periodic
            # checkpoint writer below writes into it while the scan is
            # still running, not just after save_dom_scan() at the end.
            os.makedirs(comp_dir, exist_ok=True)
            checkpoint_path = self._dom_checkpoint_path(request, safe)
            raw = scan_dom(url=url, browser=browser, headless=headless, storage_state_path=storage_state_path, auth_config=live_auth, setup_steps=setup_steps, checkpoint_path=checkpoint_path)
            paths = save_dom_scan(
                scan_data=raw,
                url=url,
                project_name=project_name,
                output_dir=comp_dir,
                module_id=module_id,
            )
            self.logger.info(f"DOM scan complete: {raw['element_count']} elements")
            # Scan finished cleanly — drop the partial checkpoint so a future
            # timed-out run doesn't promote this run's stale leftovers.
            try:
                if os.path.exists(checkpoint_path):
                    os.remove(checkpoint_path)
            except OSError:
                pass

            dom_intents_raw = _load_dom_intents_raw(paths["dom_intents"])
            self.logger.info(f"  {len(dom_intents_raw)} intents extracted")

            return {
                "dom_status": "success",
                "dom_intents_count": len(dom_intents_raw),
                "dom_intents_path": paths["dom_intents"],
                "dom_elements_path": paths["dom_elements"],
                "dom_intents_raw": dom_intents_raw,
            }

        except Exception as exc:
            self.logger.error(f"DOM scan failed: {exc}")
            return {"dom_status": "failed", "status": "failed", "error": str(exc)}

    def _read_recorded_scan(
        self, comp_dir: str, comp_root: str, url: str, project_name: str, module_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Interactive scans are recorded ahead of time via `python main.py
        --project <name> --module <id> --record` (see main.py) — a deliberate,
        visible human action outside this timed pipeline step. This method
        only reads whatever that command already wrote to disk; it never
        launches a browser, so it can never be the thing that hangs discovery.
        """
        elements_path = os.path.join(comp_dir, "dom_elements.json")
        checkpoint_path = os.path.join(comp_dir, ".scan_checkpoint.json")

        if not os.path.exists(elements_path) and os.path.exists(checkpoint_path):
            self.logger.info("  Found an interrupted recording checkpoint — promoting it to final output")
            try:
                promote_checkpoint(
                    checkpoint_path=checkpoint_path,
                    url=url,
                    project_name=project_name,
                    output_dir=comp_dir,
                    module_id=module_id,
                )
            except Exception as exc:
                self.logger.warning(f"  Checkpoint promotion failed: {exc}")

        # Read-compat: a recording made before module-scoping existed (or a
        # non-modular project) lives at the flat comprehension/ root instead.
        if not os.path.exists(elements_path) and module_id and comp_dir != comp_root:
            legacy_path = os.path.join(comp_root, "dom_elements.json")
            if os.path.exists(legacy_path):
                self.logger.info(f"  Using legacy (non-module-scoped) recording at '{comp_root}'")
                comp_dir = comp_root
                elements_path = legacy_path

        if not os.path.exists(elements_path):
            record_cmd = (
                f"python main.py --project {project_name} --module {module_id} --record"
                if module_id else
                f"python main.py --project {project_name} --record"
            )
            msg = f"No interactive recording found for this module. Run: {record_cmd}"
            self.logger.error(msg)
            return {"dom_status": "failed", "status": "failed", "error": msg}

        with open(elements_path, encoding="utf-8") as f:
            elements_doc = json.load(f)

        intents_path = os.path.join(comp_dir, "dom_intents.json")
        dom_intents_raw = _load_dom_intents_raw(intents_path)

        user_flows: list = []
        flows_path = os.path.join(comp_dir, "interactive", "user_flows.json")
        if os.path.exists(flows_path):
            try:
                with open(flows_path, encoding="utf-8") as f:
                    user_flows = json.load(f).get("flows", [])
            except Exception:
                pass

        pages = elements_doc.get("pages", [])
        total_count = elements_doc.get("total_element_count", len(elements_doc.get("elements", [])))
        self.logger.info(
            f"Interactive DOM scan: using recorded artifacts — {total_count} elements "
            f"across {len(pages)} page(s), {len(user_flows)} flow(s), "
            f"{len(dom_intents_raw)} intents"
        )

        return {
            "dom_status": "success",
            "dom_intents_count": len(dom_intents_raw),
            "dom_intents_path": intents_path,
            "dom_elements_path": elements_path,
            "dom_intents_raw": dom_intents_raw,
            "user_flows": user_flows,
            "dom_pages_count": len(pages),
        }

    def _run_synthetic_comprehension(
        self,
        dom_intents: list,
        request: dict,
        safe: str,
    ) -> Dict[str, Any]:
        """
        Rule-based fallback — converts dom_intents into business_scenarios.json + .md
        without any LLM call.  Called when ComprehensionAgent is unavailable.
        confidence_score=0.75 on all produced scenarios marks them as synthetic.
        """
        comp_dir = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        try:
            paths = synthesize_scenarios_from_dom(
                dom_intents=dom_intents,
                url=request.get("url", ""),
                application_name=request.get("application_name", safe),
                output_dir=comp_dir,
                project_name=request.get("project_name", safe),
            )
            # Count scenarios from the written JSON so we return an accurate number
            scenarios_count = 0
            try:
                import json as _json
                with open(paths["json"], encoding="utf-8") as f:
                    scenarios_count = _json.load(f).get("total_scenarios", 0)
            except Exception:
                pass
            self.logger.info(
                f"  Synthetic fallback: {scenarios_count} scenario(s) written "
                f"(confidence_score=0.75, no LLM)"
            )
            return {
                "comprehension_status": "success",
                "comprehension_source": "dom_synthesized",
                "scenarios_count": scenarios_count,
                "business_scenarios_path": paths["json"],
            }
        except Exception as exc:
            self.logger.error(f"Synthetic scenario generation failed: {exc}")
            return {"comprehension_status": "failed", "comprehension_error": str(exc)}

    def _save_intents_yaml(
        self,
        dom_intents: list,
        safe: str,
        project_name: str,
        source: str = "ui_scanner",
        module_id: Optional[str] = None,
    ) -> str:
        """
        Convert this module's DOM scan intents to intents.yaml format and
        merge-write into test_creation/intents.yaml. Downstream agents
        (TestDataAgent, ArtifactGeneratorAgent testcases, LocatorAgent, and
        SemanticMapAgent's cross-module reporting) all read from this path.

        intents.yaml is a project-wide aggregate across every module — each
        module's own dom_intents.json restarts intent_id numbering at
        DOM_INT_001, so entries are tagged with module_id here to stay
        unambiguous once merged, and every entry is a copy of exactly one
        module's dom_intents.json.

        Merge semantics (mirrors build_named_locator_map's "never wholesale
        overwrite" rule): only the entries belonging to THIS module_id are
        replaced; every other module's entries already in the file are left
        untouched. A prior single-module implementation overwrote the whole
        file on every call, which meant a multi-module project's intents.yaml
        only ever reflected whichever module was scanned most recently.

        If this module's existing entries already carry scenario mappings
        (non-empty source_scenarios — written by SemanticMapAgent or the
        legacy ArtifactGeneratorAgent testcases pass), that module's slice is
        left alone rather than reset to empty source_scenarios; other
        modules are merged in as usual.
        """
        test_creation_dir = os.path.join(_ASSETS_BASE, safe, "test_creation")
        os.makedirs(test_creation_dir, exist_ok=True)
        path = os.path.join(test_creation_dir, "intents.yaml")

        other_modules_intents: list = []
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
                existing_intents = existing.get("intents", [])
                this_module_existing = [
                    intent for intent in existing_intents
                    if intent.get("module_id") == module_id
                ]
                # Entries with no module_id at all predate this per-module
                # tagging scheme (written by the old wholesale-overwrite
                # implementation) — they are never a real "other module",
                # so they must not be preserved indefinitely once any
                # module_id-aware write happens; they're superseded here,
                # not archived under a phantom module.
                other_modules_intents = [
                    intent for intent in existing_intents
                    if intent.get("module_id") not in (module_id, None)
                ]
                if any(intent.get("source_scenarios") for intent in this_module_existing):
                    self.logger.info(
                        f"  intents.yaml: module '{module_id}' already has "
                        f"{len(this_module_existing)} scenario-mapped intent(s) — "
                        "preserving them instead of a DOM-only overwrite"
                    )
                    return path
            except Exception:
                pass  # unreadable/corrupt — fall through and rebuild from scratch

        this_module_intents = [
            {
                "intent_id": intent.get("intent_id"),
                "intent_name": intent.get("intent_name"),
                "action": intent.get("action"),
                "locator_id": intent.get("locator_id"),
                "value": intent.get("value"),
                "expected_result": intent.get("expected_result"),
                "module_id": module_id,
                "source_scenarios": [],
            }
            for intent in dom_intents
        ]

        intents_data = {
            "project": project_name,
            "source": source,
            "intents": other_modules_intents + this_module_intents,
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(intents_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        return path

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    def _check_mandatory_outputs(
        self, mode: str, safe: str, module_id: Optional[str] = None, interactive: bool = False
    ) -> List[str]:
        """Return names of mandatory files that are missing for this mode.

        For interactive-scan projects, dom_elements.json is additionally
        required and content-checked (non-empty), not just existence-checked —
        an interactive scan that captured nothing (or was never recorded)
        must block the workflow instead of silently reporting "partial".
        """
        comp_root = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        scan_dir = comprehension_scan_dir(comp_root, module_id)
        test_creation_dir = os.path.join(_ASSETS_BASE, safe, "test_creation")
        missing = []

        required = list(_MANDATORY.get(mode, []))
        if interactive and mode in ("both", "url_only") and "dom_elements.json" not in required:
            required.append("dom_elements.json")

        for fname in required:
            if fname == "intents.yaml":
                path = os.path.join(test_creation_dir, fname)
            elif fname == "dom_elements.json":
                path = os.path.join(scan_dir, fname)
            else:
                path = os.path.join(comp_root, fname)

            if not os.path.exists(path):
                missing.append(fname)
            elif fname == "dom_elements.json" and not _dom_elements_nonempty(path):
                missing.append(fname)

        return missing

    def _brd_exists(self, request: dict) -> bool:
        brd = request.get("brd_dir", "")
        if not brd:
            return False
        return os.path.isfile(brd) or os.path.isdir(brd)

    def _write_run_summary(self, result: Dict, safe: str, module_id: Optional[str] = None) -> None:
        comp_root = os.path.join(_ASSETS_BASE, safe, "test_comprehension")
        scan_dir = comprehension_scan_dir(comp_root, module_id)
        os.makedirs(scan_dir, exist_ok=True)
        # Exclude large blobs and duplicate user_flows (stored separately in interactive/user_flows.json)
        summary = {
            k: v for k, v in result.items()
            if k not in ("dom_intents_raw", "user_flows")
        }
        if module_id:
            summary["module_id"] = module_id
        # Add pointer to user_flows file if interactive scan produced them
        user_flows = result.get("user_flows", [])
        if user_flows:
            summary["user_flows_path"] = os.path.join(scan_dir, "interactive", "user_flows.json")
        path = os.path.join(scan_dir, "run_summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────
# Module-level helpers
# ──────────────────────────────────────────────────────────────────────

def _merge(comp: Dict, scan: Dict) -> Dict:
    merged = {}
    merged.update(scan)
    merged.update(comp)
    if "dom_intents_raw" in scan:
        merged["dom_intents_raw"] = scan["dom_intents_raw"]
    return merged


def _load_dom_intents_raw(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("intents", [])
    except Exception:
        return []


def _dom_elements_nonempty(path: str) -> bool:
    """True if dom_elements.json actually captured at least one element —
    used by the mandatory-output gate so an interactive scan that recorded
    nothing (empty checkpoint promotion, or a stale zero-element file) is
    treated as missing rather than silently passing."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    if data.get("elements"):
        return True
    pages = data.get("pages") or []
    if any(p.get("elements") for p in pages):
        return True
    return bool(data.get("total_element_count"))


def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"
