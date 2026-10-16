"""
ComplianceScoringAgent — final BRD Compliance Score, confidence band, verification depth,
Quality Scorecard, gates and recommendations for a run.

Pure Python (engines/scoring/v1.py): every LLM judgement already happened upstream, so the
same verdicts and findings always produce the same score, and the scoring version is stored.

Phase 9: with `agent_quality` present, its gates are appended (agent_safety_defect = block; agent_quality_gate,
agent_regression, agent_judge_unverified = warn). The compliance score itself does not change.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.evaluation.compliance_scoring.tools import recommendations, score
from tools.agent_tests.integration import apply_gates
from tools.shared import get_logger


class ComplianceScoringAgent(BaseAgent):
    MODULE_NAME = "compliance_scoring"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.compliance_scoring")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        reqs = request.get("traced_requirements") or request.get("requirements") or []
        verdicts = request.get("criterion_verdicts") or []
        findings = request.get("findings") or []
        context = {
            "runtime_possible": request.get("mode") != "brd_only" and bool(request.get("live_reachable")),
            "runtime_expected": request.get("mode") != "brd_only" and bool((request.get("live_url") or "").strip()),
            "brd_approved": False,
            "live_status": request.get("live_status"),
            "needs_credentials": bool((request.get("runtime_profile") or {}).get("needs_credentials")),
            "login_error": _login_error(request.get("runtime_profile")),
            # runtime workflow (Pass/Fail + BRD Compliance Engines)
            "runtime_counts": (request.get("pass_fail") or {}).get("counts"),
            "discrepancies": (request.get("brd_compliance") or {}).get("discrepancies") or [],
        }
        result = score(reqs, verdicts, findings, request.get("scorecard"), context)
        result = apply_gates(result, request.get("agent_quality"))  # Phase 9 gates; unchanged without agent_quality
        tests = request.get("test_cases") or []
        executed = {r.get("id"): r for r in request.get("execution_results") or []}
        result["passed"] = sum(1 for t in tests if (executed.get(t.get("id")) or {}).get("status") == "passed")
        result["failed"] = sum(1 for t in tests if (executed.get(t.get("id")) or {}).get("status") == "failed")
        result["skipped"] = len(tests) - result["passed"] - result["failed"]  # inconclusive + not executed
        recs = recommendations(reqs, verdicts, findings,
                               discrepancies=(request.get("brd_compliance") or {}).get("discrepancies") or [])
        recs = _reliability_recs((request.get("pass_fail") or {}).get("reliability")) + recs

        if result["compliance"] is None:
            emit("No scorable requirements — the BRD was written from the code, so compliance is not scored.", "warning")
        else:
            emit(f"{'BRD Compliance' if result['score_kind'] == 'brd_compliance' else 'Inferred-intent conformance'} "
                 f"{result['compliance']:.0f} ({result['ci_low']}–{result['ci_high']}), verification depth "
                 f"{result['verification_depth']:.0%}, gates: "
                 + ", ".join(f"{g['gate']} {g['level']}" for g in result["gates"]), "success")
        return {"module": self.MODULE_NAME, "status": "success", "score": result, "recommendations": recs,
                "summary": _summary(result, reqs)}


def _reliability_recs(reliability) -> list:
    """One recommendation per endpoint the app cut off with a server timeout during the run (engines/verdict/passfail)."""
    return [{"category": "flaky_behavior", "severity": "critical", "evidence_type": "scenario", "evidence_ref": e["endpoint"],
             "summary": f"Reliability: {e['endpoint']} failed with HTTP {e['status']} after about {e['after_s']}s in "
                        f"{e['cut_off']} test(s) ({', '.join(e['tests'][:6])}) while {e['succeeded']} call(s) succeeded "
                        f"(slowest {e['slowest_ok_s']}s): requests that run longer are cut off by a timeout in the app's stack "
                        "(server, proxy or ingress). Raise that timeout or run the work as a background job the page polls, "
                        "and make the work faster; the features those tests targeted could not be verified."}
            for e in reliability or []]


def _login_error(profile) -> Optional[str]:
    login = (profile or {}).get("login") or {}
    return (login.get("error") or "login failed") if login.get("attempted") and not login.get("succeeded") else None


def _summary(r: Dict, reqs) -> str:
    counts = r["verdict_counts"]
    if r["compliance"] is None:
        return ("No BRD was available and nothing could be inferred from a live app, so the requirements shown describe "
                "the code itself and are not scored. " + f"{len(reqs)} descriptive requirements were traced to code.")
    parts = [f"{'BRD compliance' if r['score_kind'] == 'brd_compliance' else 'Conformance to inferred intent'} "
             f"{r['compliance']:.0f}/100 (90% interval {r['ci_low']}–{r['ci_high']})",
             f"{r['verification_depth']:.0%} of runtime-verifiable criteria were verified at runtime"]
    verdict_bits = [f"{n} {k.replace('_', ' ')}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    parts.append("criteria: " + ", ".join(verdict_bits))
    blocks = [g["reason"] for g in r["gates"] if g["level"] == "block"]
    if blocks:
        parts.append("BLOCKED: " + "; ".join(blocks[:3]))
    return ". ".join(parts) + "."
