"""Unit tests for the BRD Compliance Engine (engines/compliance/matrix.py) and the compliance-v1.2 gates."""

from engines.compliance.matrix import build_compliance
from engines.scoring.v1 import SCORING_VERSION, recommendations, score
from engines.trace.decide import decide

REQS = [
    {"code": "REQ-01", "title": "Generate BRD", "priority": "high", "origin": "brd", "verifiability": "both", "verdict": "failed",
     "score": 0.0, "criteria": [{"code": "AC-01.1", "statement": "Generates a DOCX", "weight": 1}]},
    {"code": "REQ-02", "title": "History", "priority": "medium", "origin": "brd", "verifiability": "both", "verdict": "verified",
     "score": 0.9, "criteria": [{"code": "AC-02.1", "statement": "Lists past runs", "weight": 1}]},
    {"code": "REQ-03", "title": "Fast", "priority": "low", "origin": "brd", "verifiability": "runtime", "verdict": "partial",
     "score": 0.27, "criteria": [{"code": "AC-03.1", "statement": "Responds within 2 s", "weight": 1}]},
    {"code": "REQ-04", "title": "Export", "priority": "medium", "origin": "brd", "verifiability": "both", "verdict": "failed",
     "score": 0.0, "criteria": [{"code": "AC-04.1", "statement": "Exports PDF", "weight": 1}]},
    {"code": "REQ-05", "title": "Code", "priority": "low", "origin": "descriptive", "verdict": "implemented", "score": 0.55,
     "criteria": [{"code": "AC-05.1", "statement": "x", "weight": 1}]},
]
VERDICTS = [
    {"code": "AC-01.1", "requirement_code": "REQ-01", "verdict": "verified_fail", "resolved_verdict": "verified_fail",
     "best_strength": "E5", "credit": 0.0, "static_verdict": "implemented_static", "static_strength": "E3"},
    {"code": "AC-02.1", "requirement_code": "REQ-02", "verdict": "verified_pass", "resolved_verdict": "verified_pass",
     "best_strength": "E4", "credit": 0.9, "static_verdict": "insufficient_evidence", "static_strength": "E1"},
    {"code": "AC-03.1", "requirement_code": "REQ-03", "verdict": "partial", "resolved_verdict": "partial",
     "best_strength": "E3", "credit": 0.375, "static_verdict": "partial", "static_strength": "E3"},
    {"code": "AC-04.1", "requirement_code": "REQ-04", "verdict": "verified_fail", "resolved_verdict": "verified_fail",
     "best_strength": "E4", "credit": 0.0, "static_verdict": "partial", "static_strength": "E2"},
    {"code": "AC-05.1", "requirement_code": "REQ-05", "verdict": "implemented_static", "resolved_verdict": "implemented_static",
     "best_strength": "E2", "credit": 0.55, "static_verdict": "implemented_static", "static_strength": "E2"},
]
PF = {"counts": {"passed": 1, "failed": 2, "inconclusive": 3, "not_executed": 0, "tests": 6},
      "criteria": [{"criterion_code": "AC-01.1", "runtime_verdict": "refuted", "strength": "E5", "mixed": True},
                   {"criterion_code": "AC-02.1", "runtime_verdict": "supported", "strength": "E4", "mixed": False},
                   {"criterion_code": "AC-04.1", "runtime_verdict": "refuted", "strength": "E4", "mixed": False}],
      "tests": [{"test_code": "TC-001", "criterion_code": "AC-01.1", "scored": True, "verdict": "failed", "score": 0, "strength": "E5",
                 "reasons": ["A document was produced and downloaded — failed: no file was downloaded"],
                 "artifacts": {"bundle_id": "EV-TC-001", "screenshot": "AP-TC-001/screenshot.png", "documents": []}},
                {"test_code": "TC-002", "criterion_code": "AC-01.1", "scored": True, "verdict": "passed", "score": 90, "strength": "E4",
                 "reasons": ["ok"], "artifacts": None}]}


def test_matrix_rows_and_discrepancies():
    c = build_compliance(REQS, VERDICTS, PF, runtime_possible=True)
    row = c["matrix"][0]["criteria"][0]
    assert row["basis"] == "runtime" and row["static"]["verdict"] == "implemented_static"
    assert row["runtime"]["verdict"] == "refuted" and row["runtime"]["tests"][0]["artifacts"]["screenshot"] == "AP-TC-001/screenshot.png"
    kinds = {d["criterion_code"]: d["kind"] for d in c["discrepancies"]}
    assert kinds == {"AC-01.1": "broken_at_runtime", "AC-02.1": "missed_by_code_review",
                     "AC-03.1": "runtime_only_unverified", "AC-04.1": "broken_at_runtime"}
    assert c["discrepancies"][0]["severity"] == "high" and "no file was downloaded" in c["discrepancies"][0]["detail"]
    assert not c["matrix"][4]["scored"] and "AC-05.1" not in kinds  # descriptive requirement is not scored
    mix = c["evidence_mix"]
    assert mix["by_strength"] == {"E5": 1, "E4": 2, "E3": 1, "E2": 0, "E1": 0, "none": 0} and mix["runtime_share"] == 0.75
    assert mix["credit_by_basis"] == {"runtime": 0.706, "code": 0.294}
    assert c["counts"]["broken_at_runtime"] == 2 and c["counts"]["criteria"] == 4


def test_no_runtime_means_no_runtime_only_discrepancy():
    c = build_compliance(REQS, VERDICTS, None, runtime_possible=False)
    assert "runtime_only_unverified" not in {d["kind"] for d in c["discrepancies"]}


def test_v11_gates_and_recommendations():
    comp = build_compliance(REQS, VERDICTS, PF, runtime_possible=True)
    ctx = {"runtime_possible": True, "runtime_counts": PF["counts"], "discrepancies": comp["discrepancies"]}
    s = score(REQS, VERDICTS, [], None, ctx)
    gates = {g["gate"]: g for g in s["gates"]}
    assert SCORING_VERSION == "compliance-v1.2" and s["scoring_version"] == "compliance-v1.2"
    assert gates["high_priority_failed"]["level"] == "block"            # REQ-01 (high) — unchanged rule
    assert "AC-04.1" in gates["broken_at_runtime"]["reason"] and "AC-01.1" not in gates["broken_at_runtime"]["reason"]
    assert gates["runtime_inconclusive"]["level"] == "warn"             # 3 of 6 attempted
    none_ran = score(REQS, VERDICTS, [], None, {"runtime_counts": {"passed": 0, "failed": 0, "inconclusive": 2,
                                                                    "not_executed": 4, "tests": 6}})
    assert any(g["gate"] == "runtime_not_executed" for g in none_ran["gates"])
    behind = score(REQS, VERDICTS, [], None, {"needs_credentials": True, "runtime_counts": {"passed": 0, "failed": 0,
                                                                                           "inconclusive": 0, "not_executed": 6, "tests": 6}})
    assert {g["gate"] for g in behind["gates"]} >= {"live_behind_login"} and "runtime_not_executed" not in {g["gate"] for g in behind["gates"]}
    recs = recommendations(REQS, VERDICTS, [], discrepancies=comp["discrepancies"])
    texts = " ".join(r["summary"] for r in recs)
    assert "implemented in code but broken at runtime" in texts and "works live" in texts
    assert {r["category"] for r in recs} <= {"failed_test", "coverage_gap", "weak_validation", "missing_negative_case", "flaky_behavior"}


def test_decide_keeps_the_code_verdict_when_runtime_decides():
    static = {"status": "implemented", "valid_citations": 2, "wired": True, "negative_search_ok": True, "rationale": "found it"}
    v = decide({"code": "AC-01.1"}, {"verifiability": "both"}, static, None,
               [{"outcome": "refutes", "strength": "E5", "summary": "no document"}])
    assert v["resolved_verdict"] == "verified_fail" and v["static_verdict"] == "implemented_static" and v["static_strength"] == "E3"
    s = decide({"code": "AC-01.1"}, {"verifiability": "both"}, static, None, [])
    assert s["resolved_verdict"] == s["static_verdict"] == "implemented_static"
