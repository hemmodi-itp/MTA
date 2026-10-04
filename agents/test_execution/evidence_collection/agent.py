"""
EvidenceCollectionAgent — packages what the Playwright Executor recorded into evidence bundles.

Deterministic (engines/runtime/evidence.py): one bundle per executed plan, linked to its BRD acceptance
criterion, with the inputs sent, the output observed (text that appeared, chat reply, downloaded
documents opened and read, HTTP response), every artifact with its sha256, API/console observations
and a completeness check. Tests that were blocked or not mappable get a not-executed bundle stating
why. A manifest is written next to the artifacts. No verdicts: Output Validation and Pass/Fail use this.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.test_execution.evidence_collection.tools import collect_evidence, run_artifact_dir
from tools.shared import get_logger


class EvidenceCollectionAgent(BaseAgent):
    MODULE_NAME = "evidence_collection"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.evidence_collection")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        if request.get("mode") == "brd_only" or not (request.get("live_url") or "").strip():
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "not deployed", "evidence_collection": None}
        run, plan = request.get("execution_run"), request.get("action_plan")
        tests = request.get("test_cases") or []
        if not run and not plan and not tests:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no runtime tests were planned",
                    "evidence_collection": None}

        failures = {f["step"]: f["error"] for f in request.get("step_failures") or []}
        no_plan = failures.get("action_generation") and f"browser actions could not be generated ({failures['action_generation']})"
        col = collect_evidence(run, plan, tests, run_artifact_dir(request.get("run_id") or "adhoc"),
                               request.get("requirements") or [], execution_error=request.get("execution_error"),
                               no_plan_reason=no_plan or None)
        c = col["counts"]
        emit(f"Evidence collected: {c['bundles']} bundle(s) across {c['criteria_covered']} acceptance criteria — "
             f"{c['executed']} executed, {c['with_output']} with the expected output captured, {c['documents']} document(s) "
             f"read, {c['not_executed']} not executed.", "success" if c["with_output"] else "warning")
        gaps = [b for b in col["bundles"] if b["execution_status"] in ("completed", "failed") and b["completeness"]["missing"]]
        for b in gaps[:5]:
            emit(f"{b['test_code'] or b['plan_id']}: {'; '.join(b['completeness']['missing'])}", "warning")
        return {"module": self.MODULE_NAME, "status": "success", "evidence_collection": col}
