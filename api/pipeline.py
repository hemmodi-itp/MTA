"""
AgentEvaluationPipeline — runs workflows/agent_evaluation.yaml for one Run row.

Not an agent: it's the service-layer driver that builds each step's agent from the
shared AgentRegistry, threads outputs from step to step through one request dict,
and persists everything the frontend shows (steps, activity log, BRD, requirements,
test cases, score) to Postgres as it happens.

Execution model (see the header of workflows/agent_evaluation.yaml):
  * the workflow is a DAG — a step starts as soon as every step it `needs` has finished, so the code-evidence
    branch overlaps the browser branch;
  * a failing `critical` step stops the run; any other failure is recorded (step failed, run continues, the final
    report lists it) and its dependents degrade gracefully;
  * every step gets its own view of the request: a snapshot taken when it starts, with its own emit/progress
    callbacks (so log lines carry the right stage) and only the secrets it needs — the decrypted test account and
    the logged-in browser session go to runtime_discovery / playwright_executor, nobody else;
  * results are merged under a lock; a key written by two steps that are not ordered by the DAG is reported;
  * a heartbeat thread marks the run alive every HEARTBEAT_S seconds and picks up cancellation requests;
  * soft deadlines (timeout_s) stop waiting for a hung step: it is marked failed and its late result is dropped.

OrchestratorAgent isn't reused because it is bound to application_assets/<project>/
state files (project.yaml, project_state.json, new_additions suites) that have no
meaning for a repo submitted through the web app.
"""

import os
import shutil
import threading
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from agents.registry import AgentRegistry
from tools.agent_eval.run_store import RunStore, utcnow
from tools.agent_eval.secrets_box import decrypt_json
from tools.shared import get_logger
from workflows.workflow_loader import WorkflowDefinition, load_workflow

WORKFLOW = "agent_evaluation"
REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = Path(os.environ.get("AQP_WORKSPACE_DIR") or REPO_ROOT / ".aqp_workspace" / "runs")
HEARTBEAT_S = 30
STEP_WORKERS = 4
# set by the service on shutdown: running runs stop at the next checkpoint and go back to the queue
SERVICE_STOPPING = threading.Event()
_INTERRUPTED = "interrupted"

# registry key → (PipelineStage enum value, label shown in the UI)
STEP_META: Dict[str, tuple] = {
    "repo_fetch": ("repo_fetch", "Fetch GitHub repository"),
    "repo_analysis": ("repo_analysis", "Analyse the app's code"),
    "repo_intelligence": ("repo_intelligence", "Index repository (knowledge graph)"),
    "brd_builder": ("brd", "Locate or generate BRD → acceptance criteria"),
    "agent_test_generation": ("test_generation", "Plan runtime tests per criterion"),
    "runtime_discovery": ("runtime_discovery", "Discover the live app (browser)"),
    "app_classification": ("app_classification", "Classify the application type"),
    "action_generation": ("action_generation", "Generate browser actions per test"),
    "playwright_executor": ("playwright_execution", "Run the actions in a browser"),
    "evidence_collection": ("evidence_collection", "Collect evidence per criterion"),
    "output_validation": ("output_validation", "Validate outputs against the BRD"),
    "pass_fail": ("pass_fail", "Pass / fail verdicts"),
    "live_agent_execution": ("live_execution", "Fallback: chat/API execution"),
    "requirement_traceability": ("traceability", "Trace every criterion to code evidence"),
    "repository_review": ("review", "Review architecture, security & agent design"),
    "brd_compliance": ("brd_compliance", "BRD compliance matrix (code vs runtime)"),
    "compliance_scoring": ("scoring", "Compliance score, gates & recommendations"),
    "final_report": ("final_report", "Final evaluation report"),
}
# Keys an agent result carries that are bookkeeping, not data for later steps.
_RESULT_META_KEYS = {"module", "status", "error", "blocking", "reason", "partial_reasons"}
# Secrets: never merged into the shared request, never persisted; handed only to the steps listed.
_SECRET_KEYS = {"live_credentials": {"runtime_discovery", "playwright_executor"},
                "runtime_session": {"playwright_executor"}}


class AgentEvaluationPipeline:
    def __init__(self, settings: dict, agents_config: dict, registry: AgentRegistry, store: Optional[RunStore] = None):
        self.settings = settings
        self.agents_config = agents_config
        self.registry = registry
        self.store = store or RunStore()
        self.logger = get_logger("agent_eval.pipeline")

    def _enabled(self, step: str) -> bool:
        return self.agents_config.get("agents", {}).get(step, {}).get("enabled", True)

    # ── entry point ─────────────────────────────────────────────────────────

    def run(self, run_id: str) -> None:
        try:
            self._run(run_id)
        except Exception as exc:  # last-resort guard: a run must never stay "running" forever
            if SERVICE_STOPPING.is_set() or "after shutdown" in str(exc) or "interpreter shutdown" in str(exc):
                self._interrupted(run_id)
                return
            self.logger.error(f"[{run_id}] pipeline crashed: {exc}\n{traceback.format_exc()}")
            try:
                self._finish_failed(run_id, None, f"Internal error ({type(exc).__name__}); see the service log.",
                                    time.monotonic())
            except Exception:
                pass

    def _run(self, run_id: str) -> None:
        row = self.store.load_run(run_id)
        if row is None:
            self.logger.warning(f"[{run_id}] run not found")
            return
        started = time.monotonic()
        mode = row.get("mode") or row.get("projectMode") or "brd_and_live"
        live_url = row.get("liveUrl") or row.get("projectLiveUrl")

        wf = load_workflow(WORKFLOW)
        steps = [s for s in wf.steps if self._enabled(s) and s in STEP_META]
        self.store.ensure_steps(run_id, [{"key": STEP_META[s][0], "label": self._label(s, mode)} for s in steps])
        run = _RunState(self, run_id, row)

        secrets: Dict[str, Any] = {}
        if row.get("projectLiveAuth") and live_url and mode != "brd_only":
            try:
                secrets["live_credentials"] = decrypt_json(row["projectLiveAuth"])  # memory only, never logged
            except Exception as exc:
                self.logger.warning(f"[{run_id}] could not decrypt the live-app test account: {type(exc).__name__}")
                run.emit("The project's test account could not be decrypted (was AQP_SECRET_KEY changed?); "
                         "the live app is tested without logging in.", "warning")

        workspace = WORKSPACE_ROOT / run_id
        workspace.mkdir(parents=True, exist_ok=True)
        request: Dict[str, Any] = {
            "run_id": run_id,
            "mode": mode,
            "github_url": row["githubUrl"],
            "branch": row.get("branch"),
            "live_url": live_url,
            "has_live_credentials": bool(secrets.get("live_credentials")),
            "brd_path": row.get("brdPath") or row.get("projectBrdPath"),
            "workspace_dir": str(workspace),
            "connector_mode": (self.settings.get("llm") or {}).get("connector_mode"),
            "cancel_event": run.cancel_event,
            "step_failures": [],
            "on_test_update": run.on_test_update,
        }
        run.emit(f"Evaluation started for {row['githubUrl']} — mode: {_MODE_LABEL.get(mode, mode)}.")
        heartbeat = threading.Thread(target=run.heartbeat_loop, name=f"aqp-hb-{run_id[-6:]}", daemon=True)
        heartbeat.start()
        try:
            outcome = self._schedule(wf, steps, run, request, secrets, mode)
        finally:
            run.stopped.set()
            if not os.environ.get("AQP_KEEP_WORKSPACE"):
                shutil.rmtree(workspace, ignore_errors=True)

        if outcome == _INTERRUPTED:
            self._interrupted(run_id)
        elif outcome == "cancelled":
            self._finish_cancelled(run_id, row, started)
            run.emit("Evaluation cancelled.", "warning")
        elif outcome != "completed":
            self._finish_failed(run_id, row, outcome, started)
        else:
            self._finish_completed(run_id, row, request, started)
            failures = request["step_failures"]
            run.emit("Evaluation complete." + (f" {len(failures)} step(s) failed and are listed under the report's "
                                               "limitations." if failures else ""), "success" if not failures else "warning")

    # ── DAG scheduler ───────────────────────────────────────────────────────

    def _schedule(self, wf: WorkflowDefinition, steps: List[str], run: "_RunState", request: Dict[str, Any],
                  secrets: Dict[str, Any], mode: str) -> str:
        """Run the steps respecting `needs`; returns "completed", "cancelled" or the fatal error message."""
        enabled = set(steps)
        deps = {s: [d for d in wf.deps(s) if d in enabled] for s in steps}
        pending: List[str] = list(steps)
        running: Dict[str, tuple] = {}            # step -> (future, deadline)
        finished: Dict[str, str] = {}              # step -> status
        writers: Dict[str, str] = {}               # result key -> step that wrote it
        lock = threading.Lock()
        pool = ThreadPoolExecutor(max_workers=STEP_WORKERS, thread_name_prefix=f"aqp-step-{run.run_id[-6:]}")
        try:
            while pending or running:
                if SERVICE_STOPPING.is_set():
                    run.cancel_event.set()  # steps that honour cancellation wind down at their next checkpoint
                    run.stopped.set()
                    return _INTERRUPTED
                if run.cancel_event.is_set():
                    for s in pending:
                        self.store.step(run.run_id, STEP_META[s][0], "skipped", "Cancelled by the user.")
                    for s in running:
                        self.store.step(run.run_id, STEP_META[s][0], "failed", "Cancelled by the user.")
                    run.stopped.set()
                    return "cancelled"
                for s in [s for s in pending if all(d in finished for d in deps[s])]:
                    pending.remove(s)
                    view = self._view(s, request, secrets, run, lock)
                    self.store.step(run.run_id, STEP_META[s][0], "running")
                    self.store.update_run(run.run_id, currentStage=STEP_META[s][0],
                                          status="cloning" if s == "repo_fetch" else "running")
                    deadline = time.monotonic() + wf.timeout_s[s] if wf.timeout_s.get(s) else None
                    running[s] = (pool.submit(self._execute, s, view), deadline)

                done, _ = wait([f for f, _ in running.values()], timeout=2.0, return_when=FIRST_COMPLETED)
                for s, (fut, deadline) in list(running.items()):
                    if fut in done:
                        result = fut.result()
                    elif deadline and time.monotonic() > deadline:
                        result = {"status": "failed",
                                  "error": f"{STEP_META[s][1]} did not finish within {wf.timeout_s[s] // 60} min "
                                           "and was abandoned."}
                    else:
                        continue
                    del running[s]
                    status = self._absorb(s, result, request, secrets, writers, wf, run, lock)
                    finished[s] = status
                    if status == "failed" and s in wf.critical:
                        error = result.get("error") or f"{s} failed"
                        for later in pending:
                            self.store.step(run.run_id, STEP_META[later][0], "skipped",
                                            "Skipped — a required earlier step failed.")
                        for other in running:
                            self.store.step(run.run_id, STEP_META[other][0], "failed",
                                            "Stopped — a required earlier step failed.")
                        run.stopped.set()
                        return error
            return "completed"
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _view(self, step: str, request: Dict[str, Any], secrets: Dict[str, Any], run: "_RunState",
              lock: threading.Lock) -> Dict[str, Any]:
        """The request as this step sees it: a snapshot + its own callbacks + only its secrets."""
        stage = STEP_META[step][0]
        with lock:
            view = dict(request)
        view["emit"] = lambda message, level="info": run.emit(message, level, stage)
        view["on_progress"] = lambda detail: run.progress(stage, detail)
        for key, allowed in _SECRET_KEYS.items():
            if step in allowed and secrets.get(key) is not None:
                view[key] = secrets[key]
        return view

    def _execute(self, step: str, view: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.registry.build(step, settings=self.settings).execute(view, {}) or {}
        except Exception as exc:
            self.logger.error(f"[{view.get('run_id')}] step {step} raised: {exc}\n{traceback.format_exc()}")
            return {"status": "failed", "error": f"{STEP_META[step][1]} crashed: {type(exc).__name__}: {str(exc)[:300]}"}

    def _absorb(self, step: str, result: Dict[str, Any], request: Dict[str, Any], secrets: Dict[str, Any],
                writers: Dict[str, str], wf: WorkflowDefinition, run: "_RunState", lock: threading.Lock) -> str:
        """Merge one finished step's result, persist it and mark the step. Returns its final status."""
        stage = STEP_META[step][0]
        status = result.get("status", "success")
        for key in _SECRET_KEYS:
            if key in result:
                secrets[key] = result.pop(key)
        data = {k: v for k, v in result.items() if k not in _RESULT_META_KEYS}
        with lock:
            for key in data:
                prev = writers.get(key)
                if prev and prev != step and not _ordered(wf, prev, step):
                    self.logger.warning(f"[{run.run_id}] contract: {step} overwrote '{key}' written by unordered {prev}")
                writers[key] = step
            request.update(data)

        if status == "failed":
            error = result.get("error") or f"{step} failed"
            self.store.step(run.run_id, stage, "failed", error)
            run.emit(error, "error", stage)
            if step not in wf.critical:
                with lock:
                    request["step_failures"].append({"step": step, "label": STEP_META[step][1], "error": error})
            return "failed"
        try:
            self._persist(step, run.run_id, result, request)
        except Exception as exc:
            self.logger.error(f"[{run.run_id}] persisting {step} failed: {exc}\n{traceback.format_exc()}")
            run.emit(f"Saving the results of “{STEP_META[step][1]}” failed ({type(exc).__name__}).", "error", stage)
        if status == "skipped":
            self.store.step(run.run_id, stage, "skipped", result.get("reason") or "Not applicable")
            return "skipped"
        detail = None
        try:
            detail = self._detail(step, result)
        except Exception as exc:  # a summary line must never fail a step
            self.logger.warning(f"[{run.run_id}] detail for {step}: {exc}")
        if status == "partial" and result.get("error"):
            detail = f"Completed with warnings — {result['error']}"
        self.store.step(run.run_id, stage, "success", detail)
        return status

    # ── persistence per step ────────────────────────────────────────────────

    def _persist(self, step: str, run_id: str, result: dict, request: dict) -> None:
        s = self.store
        if step == "repo_fetch":
            s.update_run(run_id, commitRef=result.get("commit_sha"))
        elif step == "repo_analysis":
            s.update_run(run_id, agentProfile=result.get("agent_profile"))
        elif step == "repo_intelligence":
            s.update_run(run_id, snapshotId=result.get("snapshot_id"))
        elif step == "brd_builder":
            s.update_run(run_id, brdSource=result.get("brd_source"), brdPath=result.get("brd_path"),
                         brdContent=result.get("brd_markdown"), scenariosFound=len(result.get("requirements") or []))
            s.replace_requirements(run_id, result.get("requirements") or [])  # assigns DB ids in place
        elif step == "agent_test_generation":
            tests = result.get("test_cases") or []
            s.replace_test_cases(run_id, tests)  # assigns DB ids in place — later steps see them
            s.update_run(run_id, testCasesGenerated=len(tests))
        elif step in ("requirement_traceability", "brd_compliance"):
            # traceability saves the static trace; brd_compliance re-saves it with runtime evidence merged in
            if result.get("criterion_verdicts") is not None:
                s.save_criterion_verdicts(result.get("criterion_verdicts") or [])
                s.replace_evidence(run_id, result.get("evidence_items") or [])
                s.save_requirement_verdicts(result.get("traced_requirements") or [])
            if step == "brd_compliance":
                s.update_run(run_id, brdCompliance=result.get("brd_compliance"))
        elif step == "runtime_discovery":
            s.update_run(run_id, runtimeProfile=result.get("runtime_profile"))
        elif step == "app_classification":
            s.update_run(run_id, appClassification=result.get("app_classification"))
        elif step == "action_generation":
            s.update_run(run_id, actionPlan=result.get("action_plan"))
        elif step == "playwright_executor":
            s.update_run(run_id, executionRun=result.get("execution_run"))
        elif step == "evidence_collection":
            s.update_run(run_id, evidenceCollection=result.get("evidence_collection"))
        elif step == "output_validation":
            s.update_run(run_id, outputValidation=result.get("output_validation"))
        elif step == "pass_fail":
            pf = result.get("pass_fail")
            if pf:
                c = pf["counts"]
                s.update_run(run_id, passFail=pf, passed=c["passed"], failed=c["failed"],
                             skipped=c["inconclusive"] + c["not_executed"])
        elif step == "repository_review":
            s.replace_findings(run_id, result.get("findings") or [])
        elif step == "final_report":
            s.update_run(run_id, finalReport=result.get("final_report"))
        elif step == "compliance_scoring":
            sc = result["score"]
            s.update_run(
                run_id,
                scoringVersion=sc["scoring_version"], scoreKind=sc["score_kind"], complianceScore=sc["compliance"],
                ciLow=sc["ci_low"], ciHigh=sc["ci_high"], verificationDepth=sc["verification_depth"],
                scorecard=sc["scorecard"], gates=sc["gates"],
                qualityScore=sc["quality_score"], qualityBreakdown=sc["breakdown"], coveragePct=sc["coverage_pct"],
                riskLevel=sc["risk_level"], criticalDefects=sc["critical_defects"], passed=sc["passed"],
                failed=sc["failed"], skipped=sc["skipped"], summary=result.get("summary"),
            )
            s.replace_recommendations(run_id, result.get("recommendations") or [])

    @staticmethod
    def _detail(step: str, result: dict) -> Optional[str]:
        if step == "repo_fetch":
            sha = result.get("commit_sha")
            cov = result.get("repo_coverage") or {}
            extra = f" · {cov['fetched']} files" if cov.get("fetched") is not None else ""
            return f"{result.get('repo_full_name')}@{result.get('branch')}" + (f" · {sha[:7]}" if sha else "") + extra
        if step == "repo_analysis":
            profile = result.get("agent_profile") or {}
            return str(profile.get("agent_name") or profile.get("purpose") or "")[:200] or None
        if step == "repo_intelligence":
            c = (result.get("repo_model") or {}).get("counts") or {}
            return (f"{c.get('route', 0)} routes · {c.get('page', 0)} pages · {c.get('agent', 0)} agents · "
                    f"{c.get('prompt', 0)} prompts · {c.get('test', 0)} tests")
        if step in ("requirement_traceability", "brd_compliance") and result.get("criterion_verdicts") is not None \
                and step == "requirement_traceability":
            vs = result.get("criterion_verdicts") or []
            ok = sum(1 for v in vs if v["verdict"] in ("verified_pass", "implemented_static"))
            failed = result.get("llm_failures") or 0
            return (f"{ok}/{len(vs)} criteria implemented in code · "
                    f"{sum(1 for v in vs if v['verdict'] == 'insufficient_evidence')} insufficient evidence"
                    + (f" · {failed} could not be checked (LLM unavailable)" if failed else ""))
        if step == "runtime_discovery":
            p = result.get("runtime_profile") or {}
            if not p:
                return result.get("error") or result.get("reason")
            return (f"{p['app_type']} · {p['forms']} form(s) · {p['buttons']} button(s) · downloads "
                    f"{'yes' if p['downloads'] else 'no'} · chat {'yes' if p['chat_interface'] else 'no'} · "
                    f"auth {'yes' if p['authentication'] else 'no'}")
        if step == "app_classification":
            c = result.get("app_classification") or {}
            if not c:
                return result.get("reason")
            kind = c["app_type"] + (f" ({' + '.join(c['components'])})" if c.get("components") else "")
            return f"{kind} · confidence {c['confidence']:.0%} · from {c['basis']}"
        if step == "action_generation":
            ap = result.get("action_plan") or {}
            if not ap:
                return result.get("reason")
            c = ap["counts"]
            if ap["status"] == "blocked":
                return f"Blocked: {ap['reason']}"
            return (f"{c['ready']}/{c['tests']} tests ready to run · {c['unmappable']} not testable via the UI · "
                    f"{c.get('flow_checks', 0)} flow checks")
        if step == "playwright_executor":
            er = result.get("execution_run") or {}
            if not er:
                return result.get("reason") or result.get("error")
            c = er["counts"]
            return (f"{c['completed']}/{c['plans']} plans ran to the end · {c['failed']} stopped at a failing step · "
                    f"{c['downloads']} download(s) · {er['duration_s']}s")
        if step == "evidence_collection":
            ec = result.get("evidence_collection") or {}
            if not ec:
                return result.get("reason")
            c = ec["counts"]
            return (f"{c['bundles']} bundles · {c['criteria_covered']} criteria · {c['with_output']} with output captured · "
                    f"{c['documents']} document(s) read · {c['not_executed']} not executed")
        if step == "output_validation":
            ov = result.get("output_validation") or {}
            if not ov:
                return result.get("reason")
            c = ov["counts"]
            return (f"{c['validated']} validated · {c['checks_passed']} checks passed, {c['checks_failed']} failed · "
                    f"{c['meets']}/{c['judged']} judged as fully meeting the expectation")
        if step == "pass_fail":
            pf = result.get("pass_fail") or {}
            if not pf:
                return result.get("reason")
            c = pf["counts"]
            return (f"{c['passed']} passed · {c['failed']} failed · {c['inconclusive']} inconclusive · {c['not_executed']} not run · "
                    f"criteria: {c['criteria_supported']} supported, {c['criteria_refuted']} refuted")
        if step == "final_report":
            fr = (result.get("final_report") or {}).get("data") or {}
            if not fr:
                return result.get("reason")
            d = fr["decision"]
            return f"{d['outcome']}" + (f" · compliance {d['compliance']:.0f}" if d["compliance"] is not None else "") + \
                f" · {len(fr['recommendations'])} recommendations · {len(fr['limitations'])} limitations"
        if step == "brd_compliance":
            bc = result.get("brd_compliance") or {}
            if not bc:
                return result.get("reason")
            c = bc["counts"]
            return (f"{c['criteria_runtime']}/{c['criteria']} criteria proven at runtime · {c['broken_at_runtime']} broken at runtime · "
                    f"{c['missed_by_code_review']} missed by code review · {c['mixed_runtime']} inconsistent")
        if step == "repository_review":
            fs = result.get("findings") or []
            return f"{len(fs)} findings · {sum(1 for f in fs if f['severity'] in ('critical', 'high'))} critical/high"
        if step == "compliance_scoring":
            sc = result["score"]
            return (f"Compliance {sc['compliance']:.0f} · depth {sc['verification_depth']:.0%} · risk {sc['risk_level']}"
                    if sc["compliance"] is not None else "Not scored: no BRD-derived requirements")
        if step == "brd_builder":
            origin = f"found at {result.get('brd_path')}" if result.get("brd_source") == "repository" else "generated by MTA"
            return f"BRD {origin} · {len(result.get('requirements') or [])} requirements"
        if step == "agent_test_generation":
            tests = result.get("test_cases") or []
            static = len(result.get("static_only_criteria") or [])
            return f"{len(tests)} runtime tests" + (f" · {static} criteria left to code review" if static else "")
        if step == "live_agent_execution":
            res = result.get("execution_results") or []
            return f"{sum(1 for r in res if r['status'] == 'passed')}/{len(res)} passed via {result.get('transport')}"
        return None

    @staticmethod
    def _label(step: str, mode: str) -> str:
        if step == "live_agent_execution" and mode == "brd_only":
            return "Run tests on live agent (not deployed)"
        return STEP_META[step][1]

    # ── run completion ──────────────────────────────────────────────────────

    def _close_tests(self, run_id: str, reason: str) -> None:
        try:
            self.store.finalize_pending_tests(run_id, reason)
        except Exception as exc:
            self.logger.warning(f"[{run_id}] could not close pending tests: {exc}")

    def _finish_completed(self, run_id: str, row: dict, request: dict, started: float) -> None:
        failures = request.get("step_failures") or []
        self._close_tests(run_id, "the evaluation finished before this test ran"
                          + (f" ({failures[0]['label']} failed: {str(failures[0]['error'])[:200]})" if failures else ""))
        score = request.get("score") or {}
        scored = score.get("compliance") is not None
        trend = self.store.recent_scores(row["projectId"], limit=9) + ([score.get("quality_score", 0)] if scored else [])
        self.store.update_run(run_id, status="completed", finishedAt=utcnow(),
                              durationSec=int(time.monotonic() - started), trend=trend)
        if scored:
            self.store.update_project(row["projectId"], lastRunStatus="completed", lastQualityScore=score["quality_score"])
        else:  # an unscored run must not overwrite the project's score with 0
            self.store.update_project(row["projectId"], lastRunStatus="completed")

    def _finish_failed(self, run_id: str, row: Optional[dict], error: str, started: float) -> None:
        self._close_tests(run_id, f"the evaluation stopped early ({error[:200]})")
        self.store.update_run(run_id, status="failed", finishedAt=utcnow(),
                              durationSec=int(time.monotonic() - started), errorMessage=error[:2000])
        row = row or self.store.load_run(run_id)
        if row:
            self.store.update_project(row["projectId"], lastRunStatus="failed")

    def _interrupted(self, run_id: str) -> None:
        """The service stopped mid-run: queue the run again (it restarts from the beginning when the service is back)."""
        from tools.agent_eval.run_store import RESTART_MARK
        try:
            if self.store.requeue_interrupted(run_id, f"{RESTART_MARK}: the MTA service was stopped or restarted while "
                                                      "this run was in progress, so it starts again from the beginning."):
                self.store.event(run_id, "The MTA service was stopped or restarted during this run; it is queued and "
                                         "starts again automatically when the service is back.", "warning", None)
                self.logger.warning(f"[{run_id}] interrupted by a service stop; requeued")
            else:
                self._finish_failed(run_id, None, "The MTA service was stopped or restarted during this run twice in a "
                                                  "row; start a new run.", time.monotonic())
        except Exception as exc:
            self.logger.warning(f"[{run_id}] could not requeue the interrupted run: {exc}")

    def _finish_cancelled(self, run_id: str, row: dict, started: float) -> None:
        self._close_tests(run_id, "the run was cancelled")
        self.store.update_run(run_id, status="cancelled", finishedAt=utcnow(),
                              durationSec=int(time.monotonic() - started), errorMessage="Cancelled by the user.")
        self.store.update_project(row["projectId"], lastRunStatus="cancelled")


class _RunState:
    """Per-run callbacks shared by every step: logging, progress, test updates, heartbeat and cancellation."""

    def __init__(self, pipeline: AgentEvaluationPipeline, run_id: str, row: dict) -> None:
        self.pipeline, self.run_id, self.row = pipeline, run_id, row
        self.store, self.logger = pipeline.store, pipeline.logger
        self.cancel_event = threading.Event()
        self.stopped = threading.Event()

    def emit(self, message: str, level: str = "info", stage: Optional[str] = None) -> None:
        self.logger.info(f"[{self.run_id}] {message}")
        if self.stopped.is_set() and stage:
            return  # late lines from an abandoned step
        try:
            self.store.event(self.run_id, message, level, stage)
        except Exception as exc:
            self.logger.warning(f"[{self.run_id}] could not record event: {exc}")

    def progress(self, stage: str, detail: str) -> None:  # "5/16 tests done · about 33 min left" on the running step
        if self.stopped.is_set():
            return
        try:
            self.store.step_detail(self.run_id, stage, detail)
        except Exception as exc:
            self.logger.warning(f"[{self.run_id}] could not record progress: {exc}")

    def on_test_update(self, test_id: str, fields: Dict[str, Any]) -> None:
        if self.stopped.is_set():
            return
        try:
            self.store.update_test_case(test_id, **fields)
        except Exception as exc:
            self.logger.warning(f"[{self.run_id}] could not update test {test_id}: {exc}")

    def heartbeat_loop(self) -> None:
        while not self.stopped.is_set():
            try:
                if self.store.heartbeat(self.run_id):
                    if not self.cancel_event.is_set():
                        self.emit("Cancellation requested — stopping after the current action.", "warning")
                    self.cancel_event.set()
            except Exception as exc:
                self.logger.warning(f"[{self.run_id}] heartbeat failed: {exc}")
            self.stopped.wait(HEARTBEAT_S)


def _ordered(wf: WorkflowDefinition, a: str, b: str) -> bool:
    """True when one of the two steps (transitively) waits for the other."""
    def reaches(src: str, dst: str, seen: Set[str]) -> bool:
        for d in wf.deps(dst):
            if d == src or (d not in seen and (seen.add(d) or reaches(src, d, seen))):
                return True
        return False
    return reaches(a, b, set()) or reaches(b, a, set())


_MODE_LABEL = {
    "brd_and_live": "BRD + live app",
    "live_only": "live app only (BRD will be generated)",
    "brd_only": "BRD only, not deployed (code review)",
}
