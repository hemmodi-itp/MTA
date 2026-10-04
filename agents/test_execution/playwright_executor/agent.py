"""
PlaywrightExecutorAgent — runs the Action Generation Engine's plans in a real browser.

Deterministic (engines/runtime/executor.py). Reuses the session Runtime Discovery logged in with (handed on in
memory as `runtime_session`; it logs in itself only without one), then runs every ready plan in a fresh browser
context with adaptive parallelism — document generators calibrate on one generation first and drop back to one
test at a time if parallel tests slow the app down; timing-sensitive tests always run alone. Records per-step
outcomes, screenshots, page text, chat replies, downloads, network calls and console errors.
Artifacts go to a durable per-run folder (AQP_ARTIFACT_DIR, default <repo>/.aqp_artifacts/runs/<run_id>),
not the temporary workspace, so the run view can show them after the run. It does not decide
pass/fail: judged expectations are passed on to Output Validation.
"""

import shutil
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.test_execution.playwright_executor.tools import (
    BUDGET_S,
    PLAN_TIMEOUT_S,
    SERIAL_BUDGET_S,
    WORKERS,
    execute_plans,
    run_artifact_dir,
)
from engines.runtime.executor import DOC_GENERATOR_WORKERS
from tools.agent_eval.net_guard import BlockedTarget
from tools.shared import get_logger


class PlaywrightExecutorAgent(BaseAgent):
    MODULE_NAME = "playwright_executor"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.playwright_executor")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        live_url = (request.get("live_url") or "").strip()
        plan = request.get("action_plan")
        if request.get("mode") == "brd_only" or not live_url:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "not deployed", "execution_run": None}
        if not plan or plan.get("status") == "blocked":
            reason = (plan or {}).get("reason") or "no action plan"
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": reason, "execution_run": None}

        cfg = (self.settings.get("execution") or {}).get("playwright") or {}
        out = run_artifact_dir(request.get("run_id") or "adhoc")
        shutil.rmtree(out, ignore_errors=True)  # a re-run replaces this run's artifacts
        ready = sum(1 for p in plan.get("plans") or [] if p.get("status") == "ready")
        # a document generator does heavy work per test on (often) one container: calibrate on one generation,
        # then run in parallel only while that does not slow the app down (engines/runtime/executor._Slots)
        heavy = plan.get("app_type") == "Document Generator"
        workers = int(cfg.get("doc_generator_workers", DOC_GENERATOR_WORKERS) if heavy else cfg.get("workers", WORKERS))
        emit(f"Running {ready} action plan(s) in Chromium against {live_url}"
             + (f" (up to {workers} at a time, adaptive)" if workers > 1 else "") + ".")
        try:
            run = execute_plans(live_url, plan, out, credentials=request.get("live_credentials"), log=emit,
                                on_progress=request.get("on_progress"), workers=workers, calibrate=heavy,
                                storage_state=request.get("runtime_session"),
                                cancel_event=request.get("cancel_event"),
                                plan_timeout_s=int(cfg.get("plan_timeout_s", PLAN_TIMEOUT_S)),
                                budget_s=int(cfg.get("budget_s", SERIAL_BUDGET_S if heavy else BUDGET_S)))
        except BlockedTarget as exc:
            msg = f"The live URL was not opened: {exc}."
            emit(msg, "error")
            return {"module": self.MODULE_NAME, "status": "partial", "error": msg, "execution_run": None,
                    "execution_error": msg}
        except Exception as exc:
            msg = f"Browser execution failed: {type(exc).__name__}: {str(exc)[:300]}"
            emit(msg, "warning")
            # kept so Evidence Collection can say why each test did not run (instead of a bare "not executed")
            return {"module": self.MODULE_NAME, "status": "partial", "error": msg, "execution_run": None,
                    "execution_error": msg}

        c = run["counts"]
        emit(f"Executed {c['plans']} plan(s) in {run['duration_s']}s: {c['completed']} ran to the end, {c['failed']} stopped "
             f"at a failing step, {c['error'] + c['blocked'] + c['not_run']} not run; {c['downloads']} file(s) downloaded.",
             "success" if c["completed"] else "warning")
        return {"module": self.MODULE_NAME, "status": "success", "execution_run": run}
