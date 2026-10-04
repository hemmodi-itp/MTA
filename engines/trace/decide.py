"""
decide.py — turn evidence into a criterion verdict and roll criteria up into a requirement.

Evidence ladder (design doc section 4): E5 runtime + deterministic assertion · E4 runtime,
judged · E3 static + wired to an entry point (or exercised by a repo test) · E2 static only ·
E1 claim without verified evidence (never credited).

Rules, in order: runtime refutation beats everything → runtime support → non-technical
criteria excluded → the code review could not run (LLM unavailable: `llm_unavailable`, flagged
`llm_failed`, never silently `insufficient_evidence`) → static verdict (conservative of the two
verifier samples; a claimed `not_implemented` without a negative-search record — or when the index
does not cover where the code would live — becomes `insufficient_evidence` with the reason;
runtime-only criteria can reach at most `partial` statically).

`llm_unavailable` carries no credit and is excluded from the requirement score's denominator (like
`not_technically_verifiable`): the evaluation did not happen, so it must neither count as 0 nor as a pass.
"""

from typing import Dict, List, Optional

STRENGTH = {"E5": 1.0, "E4": 0.9, "E3": 0.75, "E2": 0.55, "E1": 0.0}
VALUE = {"verified_pass": 1.0, "implemented_static": 1.0, "partial": 0.5}
LLM_UNAVAILABLE = "llm_unavailable"
UNSCORED = ("not_technically_verifiable", LLM_UNAVAILABLE)  # excluded from roll-up denominators
_STATIC_ORDER = ["not_implemented", "insufficient_evidence", "partial", "implemented"]  # conservative first


def _conservative(a: str, b: Optional[str]) -> str:
    if not b:
        return a
    return min(a, b, key=lambda s: _STATIC_ORDER.index(s) if s in _STATIC_ORDER else 1)


def decide(
    criterion: Dict,
    requirement: Dict,
    static_a: Optional[Dict],
    static_b: Optional[Dict],
    runtime: List[Dict],
) -> Dict:
    """static_* = {status, valid_citations, wired, negative_search_ok, rationale[, absence_reason]} or
    {llm_failed: True, llm_error}; runtime = [{outcome, strength, summary}].

    The code-review verdict is always kept (static_verdict / static_strength / static_rationale), also when runtime
    evidence decides, so the BRD Compliance Engine can report code-vs-runtime discrepancies.
    """
    static = _static(criterion, requirement, static_a, static_b)
    refutes = [e for e in runtime if e["outcome"] == "refutes"]
    supports = [e for e in runtime if e["outcome"] == "supports"]
    if refutes:
        best = max(refutes, key=lambda e: STRENGTH[e["strength"]])
        return _with_static(_v("verified_fail", best["strength"], 1.0, best.get("summary")), static)
    if supports:
        best = max(supports, key=lambda e: STRENGTH[e["strength"]])
        return _with_static(_v("verified_pass", best["strength"], 1.0, best.get("summary")), static)
    return _with_static(static, static)


def _with_static(v: Dict, static: Dict) -> Dict:
    return {**v, "static_verdict": static["resolved_verdict"], "static_strength": static["best_strength"],
            "static_rationale": static.get("rationale")}


def _static(criterion: Dict, requirement: Dict, static_a: Optional[Dict], static_b: Optional[Dict]) -> Dict:
    """The verdict from code evidence alone."""
    if requirement.get("verifiability") == "non_technical":
        return _v("not_technically_verifiable", None, 1.0, "Process or organisational criterion; no software evidence can prove it.")
    if static_a and static_a.get("llm_failed"):
        return _v(LLM_UNAVAILABLE, None, None, static_a.get("llm_error")
                  or "The code review could not run (the LLM verifier was unavailable); this criterion was not evaluated.")
    if not static_a:
        return _v("insufficient_evidence", "E1", None, "No code review result.")

    sa, sb = static_a["status"], (static_b or {}).get("status")
    agreement = 1.0 if (not sb or sa == sb) else 0.6
    contested = {sa, sb} >= {"implemented", "not_implemented"}
    rationale = static_a.get("rationale")
    downgrade = False
    if sb and sa != sb and "insufficient_evidence" in (sa, sb) and not contested:
        # One sample found an implementation, the other only could not decide: uncertainty is not
        # contradiction. Keep the positive verdict, one strength level lower (agreement 0.6).
        primary = static_a if sa != "insufficient_evidence" else static_b
        status, downgrade = primary["status"], True
        if primary is static_b:
            static_a = {**static_b, "rationale": static_b.get("rationale") or rationale}
            rationale = static_a.get("rationale")
    else:
        status = _conservative(sa, sb)

    if status in ("implemented", "partial") and not static_a.get("valid_citations"):
        return _v("insufficient_evidence", "E1", agreement, "The code review claimed an implementation but none of its "
                  "citations could be verified in the repository.", contested)
    if status == "not_implemented":
        if not static_a.get("negative_search_ok"):
            reason = static_a.get("absence_reason")
            why = f"Not judged absent: {reason}." if reason else None
            return _v("insufficient_evidence", "E1", agreement,
                      " ".join(x for x in (why, rationale) if x) or None, contested)
        return _v("not_implemented", "E2", agreement, rationale, contested)
    if status == "insufficient_evidence":
        return _v("insufficient_evidence", "E1", agreement, rationale, contested)

    strength = "E3" if static_a.get("wired") else "E2"
    if downgrade:
        strength = "E2" if strength == "E3" else "E1"
    verdict = "implemented_static" if status == "implemented" else "partial"
    if verdict == "implemented_static" and requirement.get("verifiability") == "runtime":
        verdict = "partial"  # a latency / output-quality claim cannot be proven by reading code
        rationale = f"{rationale} (runtime-only criterion: code alone can prove at most a partial implementation)"
    return _v(verdict, strength, agreement, rationale, contested)


def _v(verdict: str, strength: Optional[str], agreement: Optional[float], rationale: Optional[str],
       contested: bool = False) -> Dict:
    credit = VALUE.get(verdict, 0.0) * STRENGTH.get(strength or "E1", 0.0)
    return {"verdict": "contested" if contested and verdict not in ("verified_pass", "verified_fail") else verdict,
            "resolved_verdict": verdict, "best_strength": strength, "credit": round(credit, 4),
            "agreement": agreement, "rationale": rationale, "llm_failed": verdict == LLM_UNAVAILABLE}


def roll_up(requirement: Dict, verdicts: List[Dict]) -> Dict:
    """Weighted credit over the requirement's criteria. Non-technical criteria and criteria whose code review could
    not run (`llm_unavailable`) are excluded from the denominator; the latter are counted in `llm_unavailable`."""
    unavailable = sum(1 for _, v in verdicts if v["resolved_verdict"] == LLM_UNAVAILABLE)
    scored = [(c, v) for c, v in verdicts if v["resolved_verdict"] not in UNSCORED]
    if not scored:
        if unavailable:
            return {"verdict": LLM_UNAVAILABLE, "score": None, "legacy_status": "unknown", "llm_unavailable": unavailable}
        return {"verdict": "not_technically_verifiable", "score": None, "legacy_status": "unknown", "llm_unavailable": 0}
    total = sum(float(c.get("weight", 1.0)) for c, _ in scored)
    score = sum(float(c.get("weight", 1.0)) * v["credit"] for c, v in scored) / total
    kinds = {v["resolved_verdict"] for _, v in scored}
    if "verified_fail" in kinds:
        verdict = "failed"
    elif kinds == {"verified_pass"}:
        verdict = "verified"
    elif kinds <= {"verified_pass", "implemented_static"}:
        verdict = "implemented"
    elif kinds & {"verified_pass", "implemented_static", "partial"}:
        verdict = "partial"
    elif kinds == {"not_implemented"}:
        verdict = "not_implemented"
    else:
        verdict = "insufficient_evidence"
    legacy = {"verified": "implemented", "implemented": "implemented", "partial": "partial",
              "failed": "missing", "not_implemented": "missing"}.get(verdict, "unknown")
    return {"verdict": verdict, "score": round(score, 4), "legacy_status": legacy, "llm_unavailable": unavailable}
