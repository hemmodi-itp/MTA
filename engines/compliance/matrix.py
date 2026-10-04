"""
matrix.py — BRD Compliance Engine: the requirement → criterion → evidence → verdict matrix.

    compliance = build_compliance(requirements, criterion_verdicts, pass_fail, runtime_possible=True)

Joins what requirement traceability decided per criterion (engines/trace/decide.py: runtime evidence first,
then code evidence) with the Pass/Fail Engine's runtime tests, and reports:

  * matrix         per requirement (priority, origin, verdict, score) → per criterion: final verdict, strength,
                   credit, basis (runtime / code / none), the code-review verdict, the runtime verdict and its
                   tests (verdict, score, strength, reason, screenshot/documents);
  * discrepancies  where code and runtime disagree or runtime is unclear:
                   broken_at_runtime        the code implements it, but it fails when the app runs  (most actionable)
                   missed_by_code_review    it works at runtime, but the code review could not find it
                   mixed_runtime            some tests for the criterion passed, others failed
                   runtime_only_unverified  only runtime can prove it (latency, output quality) and no test reached it;
  * evidence_mix   how much of the scored evidence is runtime proof (E5/E4) vs code reading (E3/E2) vs none (E1),
                   and the share of earned credit by basis;
  * counts         requirement and criterion verdicts.

The score itself stays in engines/scoring (compliance-v1.x), which reads `discrepancies` and the runtime counts for
its gates. Pure function; deterministic.
"""

from typing import Any, Dict, List, Optional, Sequence

from engines.scoring.v1 import _scored

_RUNTIME = {"E5", "E4"}
_IMPLEMENTED_IN_CODE = {"implemented_static", "partial"}
_NOT_FOUND_IN_CODE = {"not_implemented", "insufficient_evidence"}


def build_compliance(requirements: Sequence[Dict[str, Any]], criterion_verdicts: Sequence[Dict[str, Any]],
                     pass_fail: Optional[Dict[str, Any]] = None, runtime_possible: bool = False) -> Dict[str, Any]:
    by_code = {v["code"]: v for v in criterion_verdicts}
    pf_crit = {c["criterion_code"]: c for c in (pass_fail or {}).get("criteria") or []}
    pf_tests: Dict[str, List[Dict]] = {}
    for t in (pass_fail or {}).get("tests") or []:
        if t.get("scored") and t.get("criterion_code"):
            pf_tests.setdefault(t["criterion_code"], []).append(t)
    scored_codes = {r["code"] for r in _scored(requirements)}

    matrix, discrepancies = [], []
    mix = {"E5": 0, "E4": 0, "E3": 0, "E2": 0, "E1": 0, "none": 0}
    credit_by_basis = {"runtime": 0.0, "code": 0.0}
    for r in requirements:
        scored = r["code"] in scored_codes
        crit_rows = []
        for c in r.get("criteria") or []:
            v = by_code.get(c["code"]) or {}
            final = v.get("resolved_verdict") or v.get("verdict")
            strength = v.get("best_strength")
            basis = "runtime" if strength in _RUNTIME and final in ("verified_pass", "verified_fail") else \
                "code" if strength in ("E3", "E2") else "none"
            rt = pf_crit.get(c["code"])
            row = {
                "code": c["code"], "statement": c.get("statement"), "verdict": v.get("verdict"), "resolved_verdict": final,
                "strength": strength, "credit": v.get("credit"), "basis": basis, "rationale": v.get("rationale"),
                "static": {"verdict": v.get("static_verdict"), "strength": v.get("static_strength"),
                           "rationale": v.get("static_rationale")},
                "runtime": ({"verdict": rt["runtime_verdict"], "strength": rt.get("strength"), "mixed": rt.get("mixed"),
                             "tests": [_test_row(t) for t in pf_tests.get(c["code"], [])]} if rt else None),
                "discrepancy": None,
            }
            kind = _discrepancy(row, r, runtime_possible)
            if kind:
                row["discrepancy"] = kind["kind"]
                if scored:
                    discrepancies.append({**kind, "criterion_code": c["code"], "requirement_code": r["code"],
                                          "requirement_title": r.get("title"), "priority": r.get("priority")})
            if scored and final != "not_technically_verifiable":
                mix[strength if strength in mix else "none"] += 1
                if basis in credit_by_basis:
                    credit_by_basis[basis] += float(v.get("credit") or 0) * float(c.get("weight", 1))
            crit_rows.append(row)
        matrix.append({"code": r["code"], "title": r.get("title"), "priority": r.get("priority"), "origin": r.get("origin", "brd"),
                       "verifiability": r.get("verifiability"), "scored": scored, "verdict": r.get("verdict"),
                       "score": r.get("score"), "criteria": crit_rows})

    total_scored = sum(mix.values())
    earned = sum(credit_by_basis.values())
    req_counts: Dict[str, int] = {}
    for m in matrix:
        if m["scored"]:
            req_counts[m["verdict"] or "pending"] = req_counts.get(m["verdict"] or "pending", 0) + 1
    order = {"high": 0, "warning": 1, "info": 2}
    discrepancies.sort(key=lambda d: (order.get(d["severity"], 3), d["criterion_code"]))
    return {
        "matrix": matrix,
        "discrepancies": discrepancies,
        "evidence_mix": {
            "by_strength": mix,
            "runtime_share": round((mix["E5"] + mix["E4"]) / total_scored, 3) if total_scored else 0.0,
            "credit_by_basis": {k: round(v / earned, 3) if earned else 0.0 for k, v in credit_by_basis.items()},
        },
        "counts": {
            "requirements": sum(1 for m in matrix if m["scored"]), "requirement_verdicts": req_counts,
            "criteria": total_scored,
            "criteria_runtime": mix["E5"] + mix["E4"], "criteria_code_only": mix["E3"] + mix["E2"],
            "criteria_without_evidence": mix["E1"] + mix["none"],
            "broken_at_runtime": sum(1 for d in discrepancies if d["kind"] == "broken_at_runtime"),
            "missed_by_code_review": sum(1 for d in discrepancies if d["kind"] == "missed_by_code_review"),
            "mixed_runtime": sum(1 for d in discrepancies if d["kind"] == "mixed_runtime"),
            "runtime_only_unverified": sum(1 for d in discrepancies if d["kind"] == "runtime_only_unverified"),
        },
    }


def _test_row(t: Dict[str, Any]) -> Dict[str, Any]:
    return {"test_code": t.get("test_code"), "test_id": t.get("test_id"), "title": t.get("title"), "verdict": t["verdict"],
            "score": t.get("score"), "strength": t.get("strength"), "reason": (t.get("reasons") or [None])[0],
            "artifacts": t.get("artifacts")}


def _discrepancy(row: Dict[str, Any], req: Dict[str, Any], runtime_possible: bool) -> Optional[Dict[str, Any]]:
    final, static = row["resolved_verdict"], row["static"]["verdict"]
    rt = row["runtime"] or {}
    failing = next((t for t in rt.get("tests") or [] if t["verdict"] == "failed"), None)
    if final == "verified_fail" and static in _IMPLEMENTED_IN_CODE:
        return {"kind": "broken_at_runtime", "severity": "high",
                "detail": f"The code review found it {'implemented' if static == 'implemented_static' else 'partly implemented'} "
                          f"({row['static']['strength']}), but it fails when the app runs"
                          + (f": {failing['test_code']} — {failing['reason']}" if failing and failing.get("reason") else ".")}
    if final == "verified_pass" and static in _NOT_FOUND_IN_CODE:
        return {"kind": "missed_by_code_review", "severity": "info",
                "detail": f"It works on the live app, but the code review {'judged it not implemented' if static == 'not_implemented' else 'could not find it'}; "
                          "check that the BRD's wording matches the code, or point the BRD at the implementing module."}
    if rt.get("mixed"):
        return {"kind": "mixed_runtime", "severity": "warning",
                "detail": "Some runtime tests for this criterion passed and others failed; the failure decides, but the behaviour is inconsistent."}
    if (runtime_possible and req.get("verifiability") == "runtime" and final not in ("verified_pass", "verified_fail")
            and final != "not_technically_verifiable"):
        return {"kind": "runtime_only_unverified", "severity": "warning",
                "detail": "Only a runtime test can prove this (e.g. latency or output quality), and none reached it; "
                          "code evidence alone caps it at partial credit."}
    return None
