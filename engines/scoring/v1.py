"""
v1.py — BRD Compliance Score, confidence band, verification depth, Quality Scorecard and gates.

    result = score(requirements, criterion_verdicts, findings, scorecard, context)

Pure function of its inputs (bootstrap uses a fixed seed), so a stored run can be re-scored
bit-for-bit and SCORING_VERSION is persisted with every score (design doc section 12).

  Compliance = 100 · Σ p_R · score(R) / Σ p_R      p = 3/2/1 for high/medium/low priority
  score(R)   = Σ w_c · value(c) · strength(c) / Σ w_c   (criteria credits from engines/trace/decide.py)

Only requirements with origin `brd`, or `inferred` with confidence ≥ 0.5, are scored.
`insufficient_evidence` stays in the denominator with 0 credit (no inflation); non-technical
criteria and `descriptive` (code-derived) requirements are excluded and reported.

v1.1 (same score formula; new gates and recommendations from the runtime workflow): runtime tests
that could not execute or were mostly inconclusive, criteria implemented in code but broken at
runtime, and code-vs-runtime discrepancies from the BRD Compliance Engine (engines/compliance).

v1.2:
  * criteria the verifier LLM could not check (verdict `llm_unavailable` or flag `llm_failed`) are left out of
    the denominator instead of counting 0, and gated: warn when any, block when more than LLM_GAP_BLOCK of them,
    because the score would then rest on too little - re-run;
  * requirements from a BRD MTA wrote itself (`self_generated`) are scored as inferred conformance, never as BRD
    compliance;
  * a criterion the BRD extraction could not ground in the BRD text (`grounded: false`) weighs UNGROUNDED_WEIGHT of
    a grounded one, so an LLM restatement cannot carry a requirement's score;
  * `evidence_basis` says what the score rests on: "runtime+code", "code_only" (the app is deployed but no criterion
    reached runtime evidence - the report then cannot call it compliant) or "code" (not deployed).
"""

import random
from typing import Dict, List, Optional, Sequence

SCORING_VERSION = "compliance-v1.2"
LLM_GAP_BLOCK = 0.25
UNGROUNDED_WEIGHT = 0.5
PRIORITY = {"high": 3, "medium": 2, "low": 1}
_RUNTIME_STRENGTHS = {"E4", "E5"}


def _unavailable(v: Optional[Dict]) -> bool:
    """The verifier could not check this criterion (LLM failure): no evidence either way, so not scored."""
    return bool(v) and (v.get("verdict") == "llm_unavailable" or bool(v.get("llm_failed")))


def _scored(requirements: Sequence[Dict]) -> List[Dict]:
    return [r for r in requirements if r.get("origin", "brd") == "brd"
            or (r.get("origin") == "inferred" and float(r.get("confidence", 0)) >= 0.5)]


def _req_score(r: Dict, by_code: Dict[str, Dict]) -> Optional[float]:
    items = [(c, by_code.get(c["code"])) for c in r.get("criteria") or []]
    items = [(c, v) for c, v in items if v and not _unavailable(v)
             and v.get("resolved_verdict", v.get("verdict")) != "not_technically_verifiable"]
    if not items:
        return None
    w = sum(_weight(c) for c, _ in items)
    return sum(_weight(c) * float(v.get("credit") or 0) for c, v in items) / w


def _weight(c: Dict) -> float:
    return float(c.get("weight", 1)) * (UNGROUNDED_WEIGHT if c.get("grounded") is False else 1.0)


def _compliance(reqs: Sequence[Dict], scores: Dict[str, float]) -> Optional[float]:
    pairs = [(PRIORITY.get(r.get("priority"), 2), scores[r["code"]]) for r in reqs if scores.get(r["code"]) is not None]
    if not pairs:
        return None
    return 100 * sum(p * s for p, s in pairs) / sum(p for p, _ in pairs)


def score(requirements: Sequence[Dict], criterion_verdicts: Sequence[Dict], findings: Sequence[Dict],
          scorecard: Optional[Dict[str, int]], context: Dict) -> Dict:
    by_code = {v["code"]: v for v in criterion_verdicts}
    scored = _scored(requirements)
    excluded = [r["code"] for r in requirements if r not in scored]
    scores = {r["code"]: _req_score(r, by_code) for r in scored}
    compliance = _compliance(scored, scores)

    # 90% bootstrap interval over requirements (fixed seed → reproducible)
    ci = (None, None)
    valid = [r for r in scored if scores.get(r["code"]) is not None]
    if compliance is not None and len(valid) >= 3:
        rng = random.Random(1729)
        samples = sorted(_compliance([rng.choice(valid) for _ in valid], scores) for _ in range(400))
        ci = (samples[int(0.05 * len(samples))], samples[int(0.95 * len(samples)) - 1])

    # verification depth: runtime-verifiable criteria that reached runtime evidence
    runtime_crit = [c for r in scored if r.get("verifiability") in ("runtime", "both") for c in r.get("criteria") or []]
    reached = [c for c in runtime_crit if (by_code.get(c["code"]) or {}).get("best_strength") in _RUNTIME_STRENGTHS]
    depth = (len(reached) / len(runtime_crit)) if runtime_crit else 0.0

    verdict_counts: Dict[str, int] = {}
    for v in criterion_verdicts:
        verdict_counts[v["verdict"]] = verdict_counts.get(v["verdict"], 0) + 1
    insufficient_reqs = [r["code"] for r in scored if r.get("verdict") == "insufficient_evidence"]

    kind = ("brd_compliance" if any(r.get("origin") == "brd" and not r.get("self_generated") for r in scored)
            else "inferred_conformance" if scored else None)
    runtime_reached = any((v or {}).get("best_strength") in _RUNTIME_STRENGTHS for v in criterion_verdicts)
    basis = "runtime+code" if runtime_reached else "code_only" if context.get("runtime_expected") else "code"
    unavailable = [v["code"] for v in criterion_verdicts if _unavailable(v)]
    ungrounded = [c["code"] for r in scored for c in r.get("criteria") or [] if c.get("grounded") is False]
    gates = _gates(scored, by_code, findings, compliance, depth, insufficient_reqs, kind, context, excluded, requirements)
    if unavailable:
        share = len(unavailable) / max(1, len(criterion_verdicts))
        gates.insert(0, {"gate": "llm_unavailable", "level": "block" if share > LLM_GAP_BLOCK else "warn",
                         "reason": f"{len(unavailable)} of {len(criterion_verdicts)} criteria could not be checked because the "
                                   f"language model was unavailable ({', '.join(unavailable[:6])}"
                                   f"{'...' if len(unavailable) > 6 else ''}); they are left out of the score. Re-run to "
                                   "include them."})
        gates = [g for g in gates if g["gate"] != "all"]
    blocks = [g for g in gates if g["level"] == "block"]
    warns = [g for g in gates if g["level"] == "warn"]
    if blocks or (compliance is not None and compliance < 50):
        risk = "high"
    elif warns or (compliance is not None and compliance < 75):
        risk = "medium"
    else:
        risk = "low"

    covered = [r for r in valid if r.get("verdict") in ("verified", "implemented")]
    return {
        "scoring_version": SCORING_VERSION,
        "score_kind": kind,
        "compliance": round(compliance, 1) if compliance is not None else None,
        "ci_low": round(ci[0], 1) if ci[0] is not None else None,
        "ci_high": round(ci[1], 1) if ci[1] is not None else None,
        "verification_depth": round(depth, 3),
        "scorecard": scorecard,
        "gates": gates,
        "risk_level": risk,
        "critical_defects": len(blocks),
        "coverage_pct": round(100 * len(covered) / len(valid)) if valid else 0,
        "requirement_scores": {k: (round(v, 3) if v is not None else None) for k, v in scores.items()},
        "excluded_requirements": excluded,
        "verdict_counts": verdict_counts,
        "evidence_basis": basis,
        "llm_unavailable": unavailable,
        "ungrounded_criteria": ungrounded,
        # legacy dashboard fields
        "quality_score": int(round(compliance)) if compliance is not None else 0,
        "breakdown": [{"label": d.replace("_", " ").capitalize(), "score": s, "max": 100} for d, s in (scorecard or {}).items()],
    }


def _gates(scored, by_code, findings, compliance, depth, insufficient_reqs, kind, context, excluded, requirements) -> List[Dict]:
    g: List[Dict] = []
    for f in findings:
        if f.get("severity") == "critical" and f.get("source") == "scanner":
            g.append({"gate": "critical_security", "level": "block", "reason": f"{f['title']} ({f.get('file')}:{f.get('start_line')})"})
    for r in scored:
        if r.get("priority") == "high" and any((by_code.get(c["code"]) or {}).get("verdict") == "verified_fail"
                                               for c in r.get("criteria") or []):
            g.append({"gate": "high_priority_failed", "level": "block",
                      "reason": f"{r['code']} {r['title']} failed at runtime"})
    if context.get("needs_credentials") and context.get("login_error"):
        g.append({"gate": "live_login_failed", "level": "warn",
                  "reason": f"MTA tried to log in with the project's test account but it failed ({context['login_error']}), "
                            "so no runtime test ran and every criterion was judged from the code only. Check the account "
                            "on the live app's login page and re-run."})
    elif context.get("needs_credentials"):
        g.append({"gate": "live_behind_login", "level": "warn",
                  "reason": "The live app is behind a login, so MTA could not see or test it; every criterion was judged "
                            "from the code only. Add a test account to the project and re-run."})
    elif context.get("live_status") == "no_interface":
        g.append({"gate": "live_not_testable", "level": "warn",
                  "reason": "The live URL is up, but MTA found no interface it can test yet (no chat box or message API), "
                            "so no runtime test ran and every criterion was judged from the code only."})
    elif context.get("live_status") == "unreachable":
        g.append({"gate": "live_unreachable", "level": "warn",
                  "reason": "The live URL did not respond, so no runtime test ran; criteria were judged from the code only."})
    rc = context.get("runtime_counts")
    if rc and rc.get("tests") and not context.get("needs_credentials"):
        executed = rc["passed"] + rc["failed"]
        attempted = executed + rc["inconclusive"]
        if executed == 0:
            g.append({"gate": "runtime_not_executed", "level": "warn",
                      "reason": f"None of the {rc['tests']} runtime tests could be executed on the live app "
                                f"({rc['inconclusive']} inconclusive, {rc['not_executed']} not run); criteria were judged "
                                "from the code only."})
        elif attempted >= 2 and rc["inconclusive"] / attempted > 0.3:
            g.append({"gate": "runtime_inconclusive", "level": "warn",
                      "reason": f"{rc['inconclusive']} of {attempted} runtime tests were inconclusive (MTA could not drive "
                                "the UI or judge the output), so runtime coverage is thinner than planned."})
    broken = [d for d in (context.get("discrepancies") or []) if d["kind"] == "broken_at_runtime" and d.get("priority") != "high"]
    if broken:  # high-priority ones already block via high_priority_failed
        g.append({"gate": "broken_at_runtime", "level": "warn",
                  "reason": f"{len(broken)} criteria are implemented in the code but fail when the app runs: "
                            + ", ".join(d["criterion_code"] for d in broken[:8])})
    if kind is None:
        g.append({"gate": "no_scorable_requirements", "level": "warn",
                  "reason": "No BRD and no requirement inferred from the live app — the requirements shown "
                            "describe the code itself, so compliance cannot be scored. Provide a BRD or a live URL."})
    if compliance is not None and compliance < 60:
        g.append({"gate": "low_compliance", "level": "warn", "reason": f"Compliance {compliance:.0f} < 60"})
    if context.get("runtime_possible") and depth < 0.3:
        g.append({"gate": "shallow_verification", "level": "warn",
                  "reason": f"Only {depth:.0%} of runtime-verifiable criteria were verified at runtime"})
    if scored and len(insufficient_reqs) > 0.2 * len(scored):
        g.append({"gate": "insufficient_evidence", "level": "warn",
                  "reason": f"{len(insufficient_reqs)} of {len(scored)} requirements lack enough evidence: "
                            f"{', '.join(insufficient_reqs[:6])}"})
    if kind == "inferred_conformance" and not context.get("brd_approved"):
        g.append({"gate": "inferred_brd_unapproved", "level": "warn",
                  "reason": "Requirements were inferred from the live app; review and approve them to make this a BRD compliance score."})
    if not g:
        g.append({"gate": "all", "level": "pass", "reason": "No blocking or warning conditions"})
    return g


def _clip(text, n: int) -> str:
    """Shorten at a sentence or word boundary (never mid-word) and mark the cut."""
    t = " ".join(str(text or "").split())
    if len(t) <= n:
        return t
    cut = t[:n]
    end = max(cut.rfind(". "), cut.rfind("; "))
    cut = cut[:end + 1] if end > n * 0.6 else cut[:cut.rfind(" ")] if " " in cut else cut
    return cut.rstrip(" ,;:") + "…"


def recommendations(requirements: Sequence[Dict], criterion_verdicts: Sequence[Dict], findings: Sequence[Dict],
                    limit: int = 25, discrepancies: Sequence[Dict] = ()) -> List[Dict]:
    """Actionable items in the existing Recommendation shape (category/severity/summary/evidence_*)."""
    recs: List[Dict] = []
    by_req: Dict[str, List[Dict]] = {}
    for v in criterion_verdicts:
        by_req.setdefault(v.get("requirement_code"), []).append(v)
    for r in requirements:
        vs = by_req.get(r["code"], [])
        high = r.get("priority") == "high"
        failed = [v for v in vs if v["verdict"] == "verified_fail"]
        missing = [v for v in vs if v["verdict"] == "not_implemented"]
        partial = [v for v in vs if v["verdict"] in ("partial", "contested")]
        unknown = [v for v in vs if v["verdict"] == "insufficient_evidence"]
        if failed:
            recs.append({"category": "failed_test", "severity": "critical" if high else "warning", "evidence_type": "scenario",
                         "evidence_ref": r["code"], "summary": f"{r['code']} {r['title']}: failed at runtime — {_clip(failed[0].get('rationale'), 220)}"})
        if missing:
            recs.append({"category": "coverage_gap", "severity": "critical" if high else "warning", "evidence_type": "scenario",
                         "evidence_ref": r["code"], "summary": f"{r['code']} {r['title']}: not implemented ({', '.join(v['code'] for v in missing)})"})
        if partial:
            recs.append({"category": "weak_validation", "severity": "warning", "evidence_type": "scenario", "evidence_ref": r["code"],
                         "summary": f"{r['code']} {r['title']}: partially implemented ({', '.join(v['code'] for v in partial)}) — {_clip(partial[0].get('rationale'), 260)}"})
        if unknown:
            recs.append({"category": "missing_negative_case", "severity": "info", "evidence_type": "scenario", "evidence_ref": r["code"],
                         "summary": f"{r['code']} {r['title']}: no verifiable evidence for {', '.join(v['code'] for v in unknown)} — "
                                    "point the BRD at the implementing module or deploy the agent for runtime checks."})
    for d in discrepancies:
        if d["kind"] == "broken_at_runtime":
            recs.append({"category": "failed_test", "severity": "critical" if d.get("priority") == "high" else "warning",
                         "evidence_type": "scenario", "evidence_ref": d["criterion_code"],
                         "summary": f"{d['criterion_code']} ({d['requirement_code']} {d.get('requirement_title') or ''}): "
                                    f"implemented in code but broken at runtime — {_clip(d['detail'], 220)}"})
        elif d["kind"] == "mixed_runtime":
            recs.append({"category": "flaky_behavior", "severity": "warning", "evidence_type": "scenario",
                         "evidence_ref": d["criterion_code"],
                         "summary": f"{d['criterion_code']} ({d['requirement_code']}): inconsistent at runtime — some tests pass, others fail."})
        elif d["kind"] == "runtime_only_unverified":
            recs.append({"category": "coverage_gap", "severity": "info", "evidence_type": "scenario", "evidence_ref": d["criterion_code"],
                         "summary": f"{d['criterion_code']} ({d['requirement_code']}): can only be proven at runtime and no test reached it."})
        elif d["kind"] == "missed_by_code_review":
            recs.append({"category": "weak_validation", "severity": "info", "evidence_type": "scenario", "evidence_ref": d["criterion_code"],
                         "summary": f"{d['criterion_code']} ({d['requirement_code']}): works live, but its implementation could not "
                                    "be traced in the code — align the BRD's terms with the code or reference the module."})
    for f in findings:
        if f.get("verified") is False:  # an LLM finding that could not be placed in the code: not actionable
            continue
        if f.get("severity") in ("critical", "high", "medium"):
            recs.append({"category": "weak_validation", "severity": "critical" if f["severity"] == "critical" else "warning",
                         "evidence_type": "scenario", "evidence_ref": f.get("rule_id") or "review",
                         "summary": f"{f['title']}" + (f" ({f['file']}:{f['start_line']})" if f.get("file") else "") + f" — {_clip(f.get('fix'), 240)}"})
    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(recs, key=lambda r: order.get(r["severity"], 3))[:limit]
