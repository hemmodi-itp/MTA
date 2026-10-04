"""
BrdComplianceAgent — the BRD compliance matrix and code-vs-runtime discrepancies.

Deterministic (engines/compliance/matrix.py): joins requirement traceability's criterion verdicts
(runtime evidence first, then code evidence) with the Pass/Fail Engine's runtime tests into a
requirement → criterion → evidence → verdict matrix, flags where code and runtime disagree
(implemented but broken at runtime, works but not found in code, mixed runtime results,
runtime-only criteria never reached) and measures the evidence mix (E5/E4 runtime vs E3/E2 code).
Compliance scoring reads the discrepancies and runtime counts for its gates and recommendations.

Requirement traceability runs in parallel with the browser workflow, so it produces a static trace only; this step
runs after Pass/Fail (and the chat/API fallback) and first merges the runtime results into that trace
(requirement_traceability.tools.apply_runtime_evidence — runtime evidence outranks code evidence), then builds the
matrix. Its criterion_verdicts / evidence_items / traced_requirements replace the static ones downstream.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.evaluation.brd_compliance.tools import build_compliance
from agents.evaluation.requirement_traceability.tools import apply_runtime_evidence
from tools.shared import get_logger


class BrdComplianceAgent(BaseAgent):
    MODULE_NAME = "brd_compliance"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.brd_compliance")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        reqs = request.get("traced_requirements") or request.get("requirements") or []
        verdicts = request.get("criterion_verdicts") or []
        if not reqs or not verdicts:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no traced requirements", "brd_compliance": None}

        merged: Dict[str, Any] = {}
        results = request.get("execution_results") or []
        if request.get("static_trace") is not None and any(r.get("status") in ("passed", "failed") for r in results):
            merged = apply_runtime_evidence(request["static_trace"], request.get("requirements") or reqs,
                                            request.get("test_cases") or [], results)
            reqs, verdicts = merged["traced_requirements"], merged["criterion_verdicts"]
            emit(f"Merged runtime results into {sum(1 for v in verdicts if v.get('best_strength') in ('E4', 'E5'))} "
                 "criterion verdict(s).")

        result = build_compliance(reqs, verdicts, request.get("pass_fail"),
                                  runtime_possible=request.get("mode") != "brd_only" and bool(request.get("live_url")))
        c, mix = result["counts"], result["evidence_mix"]
        emit(f"Compliance matrix: {c['requirements']} requirements, {c['criteria']} criteria — {c['criteria_runtime']} proven at "
             f"runtime, {c['criteria_code_only']} from code only, {c['criteria_without_evidence']} without evidence "
             f"({mix['runtime_share']:.0%} runtime).", "success")
        if result["discrepancies"]:
            emit(f"Code vs runtime: {c['broken_at_runtime']} implemented but broken at runtime, {c['missed_by_code_review']} working "
                 f"but not found in code, {c['mixed_runtime']} inconsistent, {c['runtime_only_unverified']} runtime-only unverified.",
                 "warning" if c["broken_at_runtime"] or c["mixed_runtime"] else "info")
            for d in [d for d in result["discrepancies"] if d["severity"] == "high"][:5]:
                emit(f"{d['criterion_code']}: {d['detail'][:240]}", "warning")
        out = {"module": self.MODULE_NAME, "status": "success", "brd_compliance": result}
        if merged:
            out.update(criterion_verdicts=merged["criterion_verdicts"], evidence_items=merged["evidence_items"],
                       traced_requirements=merged["traced_requirements"])
        return out
