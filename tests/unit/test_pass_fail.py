"""Unit tests for the Pass/Fail Engine (engines/verdict/passfail.py) and the legacy-execution fallback."""

from engines.verdict.passfail import decide_all, decide_test, case_fields


def _check(cid, result, weight="core", detail="d"):
    return {"id": cid, "name": cid.replace("_", " "), "oracle": "deterministic", "result": result, "detail": detail, "weight": weight}


def _v(code="TC-001", crit="AC-01.1", checks=None, judge=None, status="validated", **kw):
    return {"bundle_id": f"EV-{code}", "test_id": f"id-{code}", "test_code": code, "criterion_code": crit, "title": "t",
            "variant": "positive", "kind": "brd_test", "scored": True, "status": status,
            "checks": checks if checks is not None else [_check("executed", "pass")], "judge": judge, **kw}


def _judge(assessment, score, unmet=()):
    return {"assessment": assessment, "score": score, "reasoning": f"judged {assessment}",
            "criteria_results": [{"criterion": u, "result": "not_met"} for u in unmet]}


def test_judge_decides_pass_and_fail():
    assert decide_test(_v(judge=_judge("meets", 95)), {})["verdict"] == "passed"
    p = decide_test(_v(judge=_judge("partially_meets", 75)), {})
    assert p["verdict"] == "passed" and p["strength"] == "E4" and p["decided_by"] == "judge"
    f = decide_test(_v(judge=_judge("partially_meets", 50, ["has a risks section"])), {})
    assert f["verdict"] == "failed" and "Not met: has a risks section" in f["reasons"]
    assert decide_test(_v(judge=_judge("cannot_tell", 50)), {})["verdict"] == "inconclusive"


def test_core_check_failure_is_a_deterministic_fail_even_if_judge_is_happy():
    v = _v(checks=[_check("executed", "pass"), _check("document_produced", "fail", detail="no file was downloaded")],
           judge=_judge("meets", 90))
    t = decide_test(v, {})
    assert t["verdict"] == "failed" and t["strength"] == "E5" and t["decided_by"] == "deterministic" and t["score"] <= 40


def test_aqp_side_and_setup_problems_are_inconclusive_not_app_failures():
    v = _v(checks=[_check("executed", "fail", detail="stopped")])
    assert decide_test(v, {"error": "element not found on /new: button “Generate”"})["verdict"] == "inconclusive"
    assert "not an app defect" in decide_test(v, {"error": "redirected to the login page (/login)"})["reasons"][0]
    hung = decide_test(v, {"error": "the app was still busy after 300s"})
    assert hung["verdict"] == "inconclusive" and "wait limit" in hung["reasons"][0]   # MTA's limit, not the app's
    timed = _v(checks=[_check("executed", "fail"), _check("time_limit", "fail", detail="slowest API call: 310.0s")])
    slow = decide_test(timed, {"error": "the app was still busy after 300s"})
    assert slow["verdict"] == "failed" and slow["strength"] == "E5"                  # a stated limit was exceeded
    other = decide_test(v, {"error": "download failed: canceled"})
    assert other["verdict"] == "failed"


def test_deterministic_oracle_passes_without_judge_but_semantic_does_not():
    v = _v(checks=[_check("executed", "pass"), _check("time_limit", "pass")])
    assert decide_test(v, {}, oracle_hint="deterministic")["verdict"] == "passed"
    t = decide_test({**v, "judge_error": "LLM down"}, {}, oracle_hint="semantic")
    assert t["verdict"] == "inconclusive" and "judge unavailable" in t["reasons"][0]


def test_supporting_failures_are_noted_not_decisive():
    v = _v(checks=[_check("executed", "pass"), _check("document_not_empty", "fail", "supporting", "12 words")],
           judge=_judge("meets", 90))
    t = decide_test(v, {})
    assert t["verdict"] == "passed" and t["supporting_issues"] == ["document not empty: 12 words"]
    assert "Also noted" in case_fields(t)["judgeReasoning"]


def test_criteria_rollup_and_legacy_results():
    ov = {"results": [
        _v("TC-001", "AC-01.1", judge=_judge("meets", 90)),
        _v("TC-002", "AC-01.1", judge=_judge("does_not_meet", 10)),
        _v("TC-003", "AC-02.1", judge=_judge("meets", 100)),
        _v("TC-004", "AC-03.1", status="not_validatable", reason="behind a login"),
        {**_v("FLOW", None, judge=None), "scored": False, "test_id": None},
    ]}
    reqs = [{"criteria": [{"code": "AC-01.1", "statement": "s1"}, {"code": "AC-02.1", "statement": "s2"}]}]
    r = decide_all(ov, {"bundles": [{"bundle_id": "EV-TC-001", "duration_ms": 5000,
                                     "observed": {"reply": "Hello there"}}]}, reqs)
    crit = {c["criterion_code"]: c for c in r["criteria"]}
    assert crit["AC-01.1"]["runtime_verdict"] == "refuted" and crit["AC-01.1"]["mixed"] and crit["AC-01.1"]["strength"] == "E4"
    assert crit["AC-02.1"]["runtime_verdict"] == "supported" and crit["AC-02.1"]["statement"] == "s2"
    assert crit["AC-03.1"]["runtime_verdict"] == "unverified"
    assert r["counts"] == {**r["counts"], "passed": 2, "failed": 1, "not_executed": 1, "tests": 4, "flow_checks": 1}
    assert r["pass_rate"] == 66.7
    legacy = {x["code"]: x for x in r["execution_results"]}
    assert legacy["TC-001"]["status"] == "passed" and legacy["TC-001"]["actual_output"] == "Hello there"
    assert legacy["TC-001"]["duration_ms"] == 5000 and legacy["TC-004"]["status"] == "not_executed"
    assert case_fields(next(t for t in r["tests"] if t["test_code"] == "TC-004"))["status"] == "not_executed"


def test_traceability_uses_pass_fail_strength():
    from agents.evaluation.requirement_traceability.agent import _runtime_evidence

    tests = [{"id": "a", "code": "TC-001", "criterion_code": "AC-01.1"}, {"id": "b", "code": "TC-002", "criterion_code": "AC-01.2"}]
    results = [{"id": "a", "status": "failed", "strength": "E5", "decided_by": "deterministic", "judge_score": 0},
               {"id": "b", "status": "inconclusive", "strength": None}]
    ev = _runtime_evidence(tests, results)
    assert ev["AC-01.1"][0]["strength"] == "E5" and ev["AC-01.1"][0]["outcome"] == "refutes"
    assert "AC-01.2" not in ev  # inconclusive is not evidence


def test_legacy_execution_only_runs_what_the_runtime_workflow_could_not():
    from agents.test_execution.live_agent_execution.agent import LiveAgentExecutionAgent

    prior = [{"id": "a", "status": "passed"}, {"id": "b", "status": "not_executed"}]
    req = {"mode": "live_only", "live_url": "https://x", "pass_fail": {"counts": {}}, "execution_results": prior,
           "test_cases": [{"id": "a", "code": "TC-001"}, {"id": "b", "code": "TC-002"}],
           "app_classification": {"app_type": "Document Generator"}}
    out = LiveAgentExecutionAgent({}).execute(req, {})
    assert out["status"] == "skipped" and out["execution_results"] == prior and "not reachable" in out["reason"]
    req["execution_results"] = [{"id": "a", "status": "passed"}, {"id": "b", "status": "failed"}]
    req["app_classification"] = {"app_type": "Chatbot"}
    out = LiveAgentExecutionAgent({}).execute(req, {})
    assert out["status"] == "skipped" and out["reason"] == "superseded by the browser workflow (Pass/Fail Engine)"


def test_positive_test_rejected_by_app_validation_is_inconclusive_not_failed():
    v = _v(checks=[_check("executed", "fail"), _check("document_produced", "fail")], judge=_judge("does_not_meet", 0))
    b = {"error": "no download was produced", "observed": {"documents": [], "messages": [],
         "ui_output": "Please add at least one point to every field before generating: Constraints, Success Metrics"}}
    t = decide_test(v, b)
    assert t["verdict"] == "inconclusive" and "not an app defect" in t["reasons"][0]
    content = {"error": "x", "observed": {"documents": [], "ui_output": "Lists are compliance-driven and must be authoritative"}}
    assert decide_test(v, content)["verdict"] == "failed"          # document wording is not a validation message
    neg = decide_test({**v, "variant": "negative"}, b)
    assert neg["verdict"] == "failed"  # decided by its own checks, not excused as a setup problem
    assert "not an app defect" not in " ".join(neg["reasons"])      # for negative tests a rejection is the expected outcome
