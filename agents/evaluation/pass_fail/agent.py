"""
PassFailAgent — final runtime verdict per test and per acceptance criterion.

Deterministic (engines/verdict/passfail.py) over Output Validation's checks and grounded judgements:
failed (app defect: a core check failed or the judge found the expectation unmet), passed, inconclusive
(MTA could not drive the UI, setup problem, or output not judgeable — never held against the app) or
not_executed. Criteria are refuted by any failed test and supported by passing ones. Updates each
TestCase row and emits `execution_results` in the shape requirement traceability and compliance
scoring already consume, with evidence strength (E5 deterministic, E4 judged).
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.evaluation.pass_fail.tools import decide_all, case_fields
from tools.shared import get_logger


class PassFailAgent(BaseAgent):
    MODULE_NAME = "pass_fail"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.pass_fail")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        update = request.get("on_test_update") or (lambda *a, **k: None)
        validation = request.get("output_validation")
        if request.get("mode") == "brd_only" or not validation:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no validated runtime output", "pass_fail": None}

        result = decide_all(validation, request.get("evidence_collection"), request.get("requirements") or [])
        for t in result["tests"]:
            if t.get("scored") and t.get("test_id"):
                update(t["test_id"], case_fields(t))

        c = result["counts"]
        emit(f"Verdicts: {c['passed']} passed, {c['failed']} failed, {c['inconclusive']} inconclusive, "
             f"{c['not_executed']} not executed (of {c['tests']} tests). Criteria at runtime: {c['criteria_supported']} "
             f"supported, {c['criteria_refuted']} refuted, {c['criteria_unverified']} unverified.",
             "success" if c["failed"] == 0 and c["passed"] else "warning")
        for t in [t for t in result["tests"] if t.get("scored") and t["verdict"] == "failed"][:5]:
            emit(f"{t['test_code']} failed: {(t['reasons'] or ['?'])[0][:240]}", "warning")
        executed = c["passed"] + c["failed"]
        out = {"module": self.MODULE_NAME, "status": "success", "pass_fail": result,
               "execution_results": result["execution_results"]}
        if executed:
            out.update(live_reachable=True, live_status="connected")
        return out
