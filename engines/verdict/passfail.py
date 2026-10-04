"""
passfail.py — Pass/Fail Engine.

    result = decide_all(output_validation, evidence_collection, requirements)

Turns Output Validation (deterministic checks + grounded judge) into one verdict per test and a runtime
verdict per acceptance criterion. It separates what the APP did wrong from what MTA could not do:

  failed        the app produced the wrong result: a core deterministic check failed (no document, wrong format,
                no reply, error status, nothing happened, time limit exceeded, the app hung or a download failed),
                or the grounded judge found the output does not meet the expectation.
  passed        no core check failed and the judge found the expectation met (or partially met with score ≥ 70);
                for a criterion whose oracle is deterministic, passing core checks alone suffice.
  inconclusive  MTA could not drive the UI (element not found, login/session problems, plan time limit),
                or the output could not be judged. Never counted against the app.
  not_executed  never started: blocked (login), not mappable to the UI, out of time or cancelled; the reason is kept.
                A run that started but crashed on MTA's side (status `error`) is inconclusive, not "not executed".

Evidence strength (design doc §4): E5 when deterministic checks decided, E4 when the judge decided.
A criterion is refuted by any failed test, supported when at least one test passed and none failed,
otherwise unverified. Unscored flow checks get verdicts but never count.

Output also includes `execution_results` in the legacy shape (id, status, judge_score, judge_reasoning, …)
so requirement traceability and compliance scoring consume runtime verdicts unchanged.
"""

import re
from typing import Any, Dict, List, Optional, Sequence

PASS_SCORE = 70
_TOOL_SIDE = re.compile(r"element not found|unknown action|plan time limit|not resolve|strict mode violation|"
                        r"target (page|closed)|browser has been closed", re.I)
_WAIT_LIMIT = re.compile(r"still busy after \d+s", re.I)
_SETUP_SIDE = re.compile(r"login failed|redirected to the login|session expired|re-login failed", re.I)
# the app's own validation rejecting MTA's input for a POSITIVE test: MTA's test data was incomplete, not an app defect
_INPUT_REJECTED = re.compile(r"^\W{0,3}please (add|fill|enter|provide|complete|select)\b|\b(this field|field|value) is required\b|"
                             r"\bare required\b|\brequired fields?\b|\bcannot be (empty|blank)\b|\bmust not be empty\b|"
                             r"\bmissing (required )?fields?\b|\bat least one\b.{0,60}\bbefore\b|^\W{0,3}[\w '-]{1,40} (is|are) required\W*$", re.I)
_RANK = {"E5": 2, "E4": 1}


def decide_test(v: Dict[str, Any], bundle: Optional[Dict[str, Any]], oracle_hint: Optional[str] = None) -> Dict[str, Any]:
    base = {k: v.get(k) for k in ("bundle_id", "test_id", "test_code", "criterion_code", "requirement_ref", "title",
                                  "variant", "kind", "scored")}
    b = bundle or {}
    out = {**base, "duration_ms": b.get("duration_ms") or 0, "actual_output": _actual_output(b), "artifacts": _links(b),
           "supporting_issues": [f"{c['name']}: {c['detail']}" for c in v.get("checks") or []
                                 if c["weight"] == "supporting" and c["result"] == "fail"]}
    if v.get("status") != "validated":
        reason = v.get("reason") or b.get("error") or "not executed"
        if b.get("execution_status") == "error":  # it ran, MTA's browser automation broke: not the app's fault
            return _done(out, "inconclusive", None, None, None, [f"MTA's browser run broke before finishing: {reason}"])
        return {**out, "verdict": "not_executed", "score": None, "strength": None, "decided_by": None,
                "reasons": [reason]}

    checks = {c["id"]: c for c in v.get("checks") or []}
    core_fail = [c for c in checks.values() if c["weight"] == "core" and c["result"] == "fail"]
    judge = v.get("judge")

    obs = b.get("observed") or {}
    produced = bool(obs.get("documents") or obs.get("reply") or (obs.get("http_response") or {}).get("status") in range(200, 300))
    rejected = next((m for m in (obs.get("messages") or []) + (obs.get("ui_output") or "").splitlines()
                     if _INPUT_REJECTED.search(m.strip()[:200])), None)
    if (v.get("variant") or "positive") == "positive" and rejected and not produced:
        return _done(out, "inconclusive", None, None, None,
                     [f"The app's validation rejected MTA's test input as incomplete (“{rejected.strip()[:200]}”); "
                      "the test data needs fixing, this is not an app defect."])

    executed = checks.get("executed")
    if executed and executed["result"] == "fail":
        err = b.get("error") or executed["detail"]
        if _SETUP_SIDE.search(err):
            return _done(out, "inconclusive", None, None, None, [f"Test setup problem, not an app defect: {err}"])
        if _TOOL_SIDE.search(err):
            return _done(out, "inconclusive", None, None, None, [f"MTA could not drive the UI: {err}"])
        if _WAIT_LIMIT.search(err) and not any(c["id"] == "time_limit" and c["result"] == "fail" for c in checks.values()):
            return _done(out, "inconclusive", None, None, None,
                         [f"The app was still working when MTA's wait limit was reached ({err}); no time limit for this "
                          "behaviour is stated, so this is not counted as a failure."])
    if core_fail:
        reasons = [f"{c['name']} — failed: {c['detail']}" for c in core_fail]
        if judge and judge.get("reasoning"):
            reasons.append(f"Judge: {judge['reasoning']}")
        return _done(out, "failed", 0 if not judge else min(judge["score"], 40), "E5", "deterministic", reasons)

    if judge:
        a, s = judge["assessment"], judge["score"]
        unmet = [c["criterion"] for c in judge.get("criteria_results") or [] if c["result"] == "not_met"]
        why = [judge.get("reasoning") or ""] + ([f"Not met: {'; '.join(unmet)}"] if unmet else [])
        if a == "meets" or (a == "partially_meets" and s >= PASS_SCORE):
            return _done(out, "passed", s, "E4", "judge", why)
        unclear = [c["criterion"] for c in judge.get("criteria_results") or [] if c["result"] == "cannot_tell"]
        if a == "partially_meets" and not unmet and unclear:
            # nothing contradicted the expectation; part of it just could not be seen in the captured output
            return _done(out, "inconclusive", s, None, "judge",
                         [f"Partly confirmed; could not be confirmed from the captured output: {'; '.join(unclear)[:400]}"] + why[:1])
        if a in ("does_not_meet", "partially_meets"):
            return _done(out, "failed", s, "E4", "judge", why)
        return _done(out, "inconclusive", s, None, "judge", ["The output could not be judged against the expectation: " + why[0]])

    if not v.get("scored") and checks:  # unscored flow check: never judged, decided by its deterministic checks
        return _done(out, "passed", 100, "E5", "deterministic", ["Flow ran and the page responded"])
    if oracle_hint == "deterministic" and checks and all(c["result"] == "pass" for c in checks.values() if c["weight"] == "core"):
        return _done(out, "passed", 100, "E5", "deterministic", ["All deterministic checks passed: " +
                                                                 "; ".join(c["name"] for c in checks.values() if c["weight"] == "core")])
    reason = v.get("judge_error") and f"judge unavailable ({v['judge_error']})" or "no output to judge"
    return _done(out, "inconclusive", None, None, None, [f"Output captured but not judged: {reason}"])


def _done(out, verdict, score, strength, decided_by, reasons):
    return {**out, "verdict": verdict, "score": score, "strength": strength, "decided_by": decided_by,
            "reasons": [r for r in reasons if r]}


def _links(b: Dict[str, Any]) -> Dict[str, Any]:
    """Artifact paths (relative to the run's artifact folder) that prove this verdict, for evidence citations."""
    arts = b.get("artifacts") or []
    shot = next((a["path"] for a in arts if a["type"] == "screenshot"), None) \
        or next((a["path"] for a in arts if a["type"] == "failure_screenshot"), None)
    docs = [{"name": d.get("name"), "file": d.get("file"), "text_file": d.get("text_file")}
            for d in (b.get("observed") or {}).get("documents") or [] if d.get("file")]
    return {"bundle_id": b.get("bundle_id"), "screenshot": shot, "documents": docs}


def _actual_output(b: Dict[str, Any]) -> Optional[str]:
    o = b.get("observed") or {}
    if o.get("reply"):
        return o["reply"][:4000]
    docs = [d for d in o.get("documents") or []]
    if docs:
        lines = [f"{d.get('name')} ({d.get('format') or '?'}, {d.get('words') or 0} words)"
                 + ("" if d.get("readable") else f" — unreadable: {d.get('error')}") for d in docs]
        excerpt = next((d.get("text_excerpt") for d in docs if d.get("text_excerpt")), "")
        return ("Downloaded: " + "; ".join(lines) + ("\n\n" + excerpt[:2500] if excerpt else ""))[:4000]
    if o.get("http_response"):
        r = o["http_response"]
        return f"HTTP {r.get('status')}: {(r.get('excerpt') or '')[:3500]}"
    if o.get("ui_output") or o.get("messages"):
        return ((o.get("ui_output") or "") + ("\n" + "\n".join(o["messages"]) if o.get("messages") else ""))[:4000]
    return None


def decide_all(output_validation: Optional[Dict[str, Any]], evidence_collection: Optional[Dict[str, Any]],
               requirements: Sequence[Dict[str, Any]] = ()) -> Dict[str, Any]:
    bundles = {b["bundle_id"]: b for b in (evidence_collection or {}).get("bundles") or []}
    hints = {c["code"]: c.get("oracle_hint") for r in requirements for c in (r.get("criteria") or []) if c.get("code")}
    statements = {c["code"]: c.get("statement") for r in requirements for c in (r.get("criteria") or []) if c.get("code")}
    tests = [decide_test(v, bundles.get(v["bundle_id"]), hints.get(v.get("criterion_code")))
             for v in (output_validation or {}).get("results") or []]
    scored = [t for t in tests if t.get("scored")]

    criteria: Dict[str, Dict[str, Any]] = {}
    for t in scored:
        code = t.get("criterion_code")
        if not code:
            continue
        c = criteria.setdefault(code, {"criterion_code": code, "statement": statements.get(code), "tests": [],
                                       "passed": 0, "failed": 0, "inconclusive": 0, "not_executed": 0})
        c["tests"].append(t["test_code"])
        c[t["verdict"]] += 1
    for code, c in criteria.items():
        deciding = [t for t in scored if t.get("criterion_code") == code and t["verdict"] in ("passed", "failed")]
        if c["failed"]:
            c["runtime_verdict"] = "refuted"
            deciding = [t for t in deciding if t["verdict"] == "failed"]
        elif c["passed"]:
            c["runtime_verdict"] = "supported"
        else:
            c["runtime_verdict"] = "unverified"
        c["strength"] = max((t["strength"] for t in deciding if t["strength"]), key=lambda s: _RANK[s], default=None)
        c["mixed"] = bool(c["passed"] and c["failed"])

    counts = {v: sum(1 for t in scored if t["verdict"] == v) for v in ("passed", "failed", "inconclusive", "not_executed")}
    counts.update(tests=len(scored), flow_checks=len(tests) - len(scored),
                  criteria_supported=sum(1 for c in criteria.values() if c["runtime_verdict"] == "supported"),
                  criteria_refuted=sum(1 for c in criteria.values() if c["runtime_verdict"] == "refuted"),
                  criteria_unverified=sum(1 for c in criteria.values() if c["runtime_verdict"] == "unverified"))
    executed = counts["passed"] + counts["failed"]
    return {"counts": counts, "pass_rate": round(100 * counts["passed"] / executed, 1) if executed else None,
            "tests": tests, "criteria": sorted(criteria.values(), key=lambda c: c["criterion_code"]),
            "execution_results": [legacy_result(t) for t in scored if t.get("test_id")]}


def legacy_result(t: Dict[str, Any]) -> Dict[str, Any]:
    """The shape requirement traceability / compliance scoring already read (live_agent_execution's results)."""
    status = {"passed": "passed", "failed": "failed"}.get(t["verdict"], "not_executed" if t["verdict"] == "not_executed" else "inconclusive")
    reasoning = " ".join(t.get("reasons") or [])
    return {"id": t["test_id"], "code": t["test_code"], "status": status, "judge_score": t.get("score"),
            "judge_reasoning": reasoning, "duration_ms": t.get("duration_ms") or 0, "actual_output": t.get("actual_output"),
            "error_summary": None if t["verdict"] in ("passed", "failed") else reasoning[:500],
            "transport_error": False, "strength": t.get("strength"), "decided_by": t.get("decided_by"),
            "source": "runtime_workflow", "artifacts": t.get("artifacts")}


def case_fields(t: Dict[str, Any]) -> Dict[str, Any]:
    """TestCase columns for the run's Tests tab."""
    status = {"passed": "passed", "failed": "failed", "not_executed": "not_executed"}.get(t["verdict"], "inconclusive")
    reasoning = " ".join(t.get("reasons") or [])
    if t.get("supporting_issues"):
        reasoning += " Also noted: " + "; ".join(t["supporting_issues"])
    return {"status": status, "judgeScore": t.get("score"), "judgeReasoning": reasoning[:4000] or None,
            "actualOutput": t.get("actual_output"), "durationMs": int(t.get("duration_ms") or 0),
            "errorSummary": None if t["verdict"] in ("passed", "failed")
            else (("Inconclusive: " if t["verdict"] == "inconclusive" else "Not executed: ") + reasoning)[:1000]}
