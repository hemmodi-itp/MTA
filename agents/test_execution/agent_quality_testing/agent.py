"""
AgentQualityTestingAgent — Phase 9 AI-agent / chatbot testing in the agent-evaluation DAG.

Runs the project's golden dataset (eval_sets/<agent>/, registered in eval_sets/index.yaml — the per-project opt-in)
against the live agent: every dimension of Phase 9.1 (task success, groundedness, hallucination, consistency,
robustness, multi-turn, format, scope, direct / indirect prompt injection, data leakage, harmful requests, tool use,
session isolation, latency / cost), deterministic checks first, the LLM judge (a model different from the agent's)
only for what they cannot decide, k runs per case with Wilson statistical verdicts, and a regression comparison with
the previous run of the same agent.

Never overwrites a recorded result: it writes only `agent_quality` / `agent_quality_rows` (appended as new
TestCase rows by the pipeline). It skips — with the reason — when the app is not deployed, is not a chat / agent /
API app, has no registered eval set, or its eval set is invalid. Every request goes through the guarded transport
(public hosts only); red-team dimensions need the eval set's explicit authorization.
"""

import json
import os
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.test_execution.agent_quality_testing.tools import (
    BlockedTarget,
    Calibration,
    HttpTransport,
    Judge,
    JudgeModelConflict,
    RunTokens,
    agent_dir,
    check_target,
    integration,
    load_cases,
    make_llm,
    read_manifest,
    regression,
    run_suite,
    spec_for,
)
from tools.shared import get_logger

DEFAULT_WORKERS = 4


class AgentQualityTestingAgent(BaseAgent):
    MODULE_NAME = "agent_quality_testing"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.agent_quality_testing")

    def _skip(self, reason: str, emit) -> Dict[str, Any]:
        emit(f"AI agent quality tests skipped: {reason}.")
        return {"module": self.MODULE_NAME, "status": "skipped", "reason": reason, "agent_quality": None,
                "agent_quality_rows": []}

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        why = integration.not_applicable(request)
        if why:
            return self._skip(why, emit)
        root = (self.settings.get("agent_tests") or {}).get("eval_sets_dir")
        agent = integration.resolve_eval_set(request.get("github_url"), root)
        if not agent:
            return self._skip("no eval set is registered for this repository (eval_sets/index.yaml)", emit)
        directory = agent_dir(agent, root)
        try:
            spec = spec_for(directory)
        except Exception as exc:
            return {**self._skip(f"eval set {agent!r} has an invalid agent.yaml", emit), "status": "failed",
                    "error": f"eval set {agent!r}: {exc}"[:500]}
        if not spec.enabled:
            return self._skip(f"eval set {agent!r} is disabled (agent.yaml enabled: false)", emit)
        cases, rep = load_cases(directory)
        if rep.errors:
            return {**self._skip(f"eval set {agent!r} has errors", emit), "status": "failed",
                    "error": "; ".join(rep.errors[:3])[:500]}
        live_url = request["live_url"].strip()
        try:
            check_target(live_url)
        except BlockedTarget as exc:
            return self._skip(f"the live URL is not allowed ({exc})", emit)

        judge = None
        try:
            judge = Judge(make_llm(spec.judge.connector, spec.judge.model), Calibration.load(directory),
                          agent_model=spec.agent_model, escalate=spec.judge.escalate)
        except JudgeModelConflict as exc:
            emit(f"No LLM judge: {exc}. Only deterministic verdicts are reported.", "warning")
        run_id = request.get("run_id") or "run"
        tokens = RunTokens.derive(0, run_id, system_canary=spec.canaries.system_prompt_value).as_dict()
        cancel = request.get("cancel_event")
        emit(f"AI agent quality: {len(cases)} golden case(s) of eval set {agent!r} against {live_url}"
             + (f", judge {judge.model}" if judge else "") + ".")
        workers = int((self.settings.get("agent_tests") or {}).get("workers") or DEFAULT_WORKERS)
        result = run_suite(spec, cases, HttpTransport(live_url, spec.transport), tokens, run_id, k=None,
                           emit=lambda m: emit(m, "warning"), judge=judge, workers=workers,
                           stop=(lambda: cancel.is_set()) if cancel is not None else None)

        path = regression.history_path(agent)
        entry = regression.history_entry(result, (read_manifest(directory) or {}).get("dataset_version"))
        reg = regression.compare(entry, regression.last_entry(path, exclude_run=run_id),
                                 spec.regression.max_drop_points)
        regression.append(path, entry)
        artifact = self._write_artifact(run_id, {**result, "regression": reg})
        aq = integration.summarize(result, reg, agent, spec, artifact)
        failing = [d for d, v in aq["dimensions"].items() if v["outcome"] == "fail"]
        emit(f"AI agent quality: {result['requests']} request(s); "
             + (f"defects in {', '.join(failing)}" if failing else "no defect observed")
             + (f"; regression in {', '.join(r['dimension'] for r in reg['regressions'])}" if not reg["ok"] else "")
             + ".", "warning" if failing or not reg["ok"] else "success")
        return {"module": self.MODULE_NAME, "status": "success", "agent_quality": aq,
                "agent_quality_rows": integration.test_case_rows(result)}

    def _write_artifact(self, run_id: str, data: Dict[str, Any]) -> Optional[str]:
        try:
            from engines.runtime.paths import artifact_root
            folder = artifact_root() / run_id
            os.makedirs(folder, exist_ok=True)
            path = folder / "agent_quality.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, default=str)
            return str(path)
        except Exception as exc:  # the verdicts are already in the result; a full disk must not fail the step
            self.logger.warning(f"could not write agent_quality.json: {exc}")
            return None
