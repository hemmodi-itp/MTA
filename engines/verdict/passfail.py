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
  inconclusive  MTA could not drive the UI (element not found, login/session problems, plan time limit), the app's
                request was cut off by a server timeout (a 5xx slower than every success of the same endpoint in the
                run: reported once as a reliability defect, see `reliability`), the app's form validation stopped a
                negative test that is not about validation, the live
                app could not be reached (outage, connection timeout), the app's AI provider refused for quota
                (429 / RESOURCE_EXHAUSTED), or the output could not be judged.
                Never counted against the app.
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

from engines.runtime.outage import RATE_LIMITED, UNREACHABLE
from engines.runtime.rejection import INPUT_REJECTED as _INPUT_REJECTED

PASS_SCORE = 70
MIN_CUTOFF_MS = 5_000
_TOOL_SIDE = re.compile(r"element not found|unknown action|plan time limit|not resolve|strict mode violation|"
                        r"target (page|closed)|browser has been closed", re.I)
_WAIT_LIMIT = re.compile(r"still busy after \d+s", re.I)
_SETUP_SIDE = re.compile(r"login failed|redirected to the login|session expired|re-login failed", re.I)
_REJECTED_STEP = re.compile(r"rejected the submitted input: “([^”]+)", re.I)
_RANK = {"E5": 2, "E4": 1}


# an expectation about the app's own input checking: a validation message is then the behaviour under test
_ABOUT_VALIDATION = re.compile(r"\b(validat\w*|required|mandatory|missing|empty|blank|invalid|reject\w*|not allowed|"
                               r"must (be|contain|have)|error message for (the )?(field|input))\b", re.I)


_ID_SEGMENT = re.compile(r"^(\d{3,}|[0-9a-f]{8,}|[0-9a-f]{8}(-[0-9a-f]{4,}){1,4}|\d{8}-\d{6}(-\w+)?|[A-Za-z0-9_-]{20,})$", re.I)


def _route(method: Any, path: Any) -> str:
    """'POST /api/runs/20261017-085202-9dff67/diagrams' → 'POST /api/runs/{id}/diagrams': one endpoint, whichever run."""
    segs = [("{id}" if _ID_SEGMENT.match(s) else s) for s in str(path or "").split("/")]
    return f"{method} {'/'.join(segs)}"


def server_cutoffs(bundles: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """bundle_id -> the server failure that cut this test's request off: a 5xx (or a connection the app dropped) from an
    endpoint that answered 2xx in other tests of the same run, arriving no earlier than its typical (median) success.
    The app had been working as long as a normal success takes, so a timeout in its stack ended it; the feature under
    test was not reached. A crash answers fast and stays a failure. A fixed timeout sits near the slowest successes
    (BRD_Agent: 500s at 181 s while one success took 183 s), so "slower than every success" would miss most of them."""
    ok: Dict[str, List[int]] = {}
    for b in bundles:
        for n in (b.get("observations") or {}).get("api_ok") or []:
            ok.setdefault(_route(n["method"], n["path"]), []).append(n["ms"])
    out = {}
    for b in bundles:
        for n in (b.get("observations") or {}).get("api_failures") or []:
            key, status = _route(n.get("method"), n.get("path")), n.get("status") or 0
            if not ok.get(key) or not (status >= 500 or status == 0):
                continue
            typical = sorted(ok[key])[len(ok[key]) // 2]
            if n.get("ms", 0) >= max(typical, MIN_CUTOFF_MS):  # a timeout is never instant (status 0 after 0 s = a cancelled load)
                out[b["bundle_id"]] = {"endpoint": key, "status": status or "dropped connection", "ms": n["ms"],
                                       "ok_calls": len(ok[key]), "max_ok_ms": max(ok[key]), "typical_ok_ms": typical}
                break
    return out


def _status_text(status: Any) -> str:
    return f"HTTP {status}" if isinstance(status, int) else str(status)


def decide_test(v: Dict[str, Any], bundle: Optional[Dict[str, Any]], oracle_hint: Optional[str] = None,
                cutoff: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
    produced = bool(obs.get("documents") or obs.get("views") or obs.get("reply")
                    or (obs.get("http_response") or {}).get("status") in range(200, 300))
    # the executor ends a positive test whose submit the app rejected with "the app rejected the submitted input: “…”"
    said = _REJECTED_STEP.search(str(b.get("error") or ""))
    rejected = next((m for m in ([said.group(1)] if said else []) + (obs.get("messages") or [])
                     + (obs.get("ui_output") or "").splitlines() if _INPUT_REJECTED.search(m.strip()[:200])), None)
    if (v.get("variant") or "positive") == "positive" and rejected and not produced:
        return _done(out, "inconclusive", None, None, None,
                     [f"The app's validation rejected MTA's test input as incomplete (“{rejected.strip()[:200]}”); "
                      "the test data needs fixing, this is not an app defect."])
    expectation = " ".join(str(x.get(k) or "") for x in (v, b) for k in ("expected_behavior", "criterion_statement"))
    if rejected and not produced and expectation.strip() and not _ABOUT_VALIDATION.search(expectation):
        # a negative / robustness test about something else (e.g. how a generation failure is reported): the app's form
        # validation stopped it before the behaviour under test was reached
        return _done(out, "inconclusive", None, None, None,
                     [f"The app's form validation stopped the test (“{rejected.strip()[:200]}”) before the behaviour "
                      "under test was reached, so it shows nothing about this criterion."])
    if cutoff and not produced and "time_limit" not in checks:
        return _done(out, "inconclusive", None, None, None,
                     [f"The app's {cutoff['endpoint']} failed ({_status_text(cutoff['status'])}) after "
                      f"{cutoff['ms'] / 1000:.0f}s, as long as its {cutoff['ok_calls']} successful calls in this run "
                      f"typically take ({cutoff.get('typical_ok_ms', cutoff['max_ok_ms']) / 1000:.0f}s; slowest "
                      f"{cutoff['max_ok_ms'] / 1000:.0f}s): the request was cut off by a timeout in the app before the "
                      "feature under test was reached. Reported as a reliability defect; this criterion is unverified by "
                      "this test."])
    unset_own = [u["field"] for u in b.get("unset_inputs") or [] if not u.get("synthetic")]

    executed = checks.get("executed")
    if executed and executed["result"] == "fail":
        err = b.get("error") or executed["detail"]
        if UNREACHABLE.search(err):
            return _done(out, "inconclusive", None, None, None,
                         [f"The live app could not be reached during this test ({err[:200]}); an outage says nothing "
                          "about the requirement, so it is not counted against the app."])
        if RATE_LIMITED.search(err):
            return _done(out, "inconclusive", None, None, None,
                         [f"The app's AI provider refused the request for quota / rate limits ({err[:240]}); the "
                          "deployment ran out of capacity, which says nothing about this requirement."])
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
        if a in ("does_not_meet", "partially_meets") and unset_own:
            # the test's own input did not all reach the app, so the output cannot be held against the expectation
            return _done(out, "inconclusive", s, None, "judge",
                         [f"MTA could not set {', '.join(unset_own[:4])}, which the test specified; the output was judged "
                          "without it, so a shortfall says nothing certain about the app."] + why[:1])
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
    cutoffs = server_cutoffs(list(bundles.values()))
    tests = [decide_test(v, bundles.get(v["bundle_id"]), hints.get(v.get("criterion_code")), cutoffs.get(v["bundle_id"]))
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
            "reliability": _reliability(cutoffs, list(bundles.values()), {t["bundle_id"]: t.get("test_code") for t in tests}),
            "execution_results": [legacy_result(t) for t in scored if t.get("test_id")]}


def _reliability(cutoffs: Dict[str, Dict[str, Any]], bundles: List[Dict[str, Any]], codes: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per endpoint: how often the app's request was cut off by a server timeout during the run (an app defect of its own,
    reported once instead of being blamed on every feature whose test it interrupted)."""
    out: Dict[str, Dict[str, Any]] = {}
    for bid, c in cutoffs.items():
        e = out.setdefault(c["endpoint"], {"endpoint": c["endpoint"], "status": c["status"], "status_text": _status_text(c["status"]),
                                           "cut_off": 0, "tests": [],
                                           "after_s": [], "succeeded": c["ok_calls"], "slowest_ok_s": round(c["max_ok_ms"] / 1000)})
        e["cut_off"] += 1
        e["tests"].append(codes.get(bid) or bid)
        e["after_s"].append(round(c["ms"] / 1000))
    for e in out.values():
        e["after_s"] = sorted(e["after_s"])[len(e["after_s"]) // 2]  # median
    return sorted(out.values(), key=lambda e: -e["cut_off"])


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
