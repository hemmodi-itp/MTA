import json

from tools.reporting import summary as qs

TRACE = {"summary": {"coverage_pct": 50.0, "acs_covered": 1, "acs_automatable": 2},
         "acs": [{"id": "AC-1", "priority": "P0", "statement": "s", "status": "covered", "children": [],
                  "tests": [{"tc_id": "T1", "title": "t1", "status": "passed"}]},
                 {"id": "AC-2", "priority": "P1", "statement": "s2", "status": "uncovered", "children": [],
                  "uncovered_reason": {"code": "missing_locator", "detail": "x"}, "tests": []}],
         "uncovered": [{"id": "AC-2", "priority": "P1", "code": "missing_locator", "detail": "x"}]}
PLANS = {"plans": {"S": {"tests": [{"tc_id": "T1", "priority": "P0"}, {"tc_id": "T2", "priority": "P0"},
                                   {"tc_id": "T3", "priority": "P1"}]}}}
RESULTS = [{"tc_id": "T1", "pw_status": "passed"}, {"tc_id": "T2", "pw_status": "failed", "tags": ["@a11y"]},
           {"tc_id": "T3", "pw_status": "skipped"}]


def test_summary_metrics():
    s = qs.compute_summary(RESULTS, TRACE, PLANS, {"specs": [{"weak_oracle": ["a", "b"]}]},
                           {"counts": {"product_defect": 3}}, None)
    assert s["pass_rate_by_priority"]["P0"] == {"passed": 1, "executed": 2, "rate": 50.0}
    assert s["pass_rate_by_priority"]["P1"] is None          # skipped is not executed
    assert (s["requirement_coverage"], s["weak_oracle"], s["product_defects"], s["a11y_findings"]) == (50.0, 2, 3, 1)


def test_csv_export():
    rows = qs.traceability_csv(TRACE).splitlines()
    assert rows[1].startswith("AC-1,P0,s,covered,T1,t1,passed")
    assert rows[2].endswith("not_run,missing_locator")


def test_gate_exit_code(tmp_path):
    s = qs.compute_summary(RESULTS, TRACE, PLANS, {}, None, None)
    fail = qs.evaluate_gates(s, qs.gates_config({"quality_gates": {"p0_pass_rate": 100, "requirement_coverage": 40}}))
    assert fail["verdict"] == "FAIL" and qs.gate_exit_code(fail) == 1
    ok = qs.evaluate_gates(s, {"requirement_coverage": 40})
    assert ok["verdict"] == "PASS" and qs.gate_exit_code(ok) == 0
    assert qs.gate_exit_code(qs.evaluate_gates(s, {})) == 0   # no gates configured
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"quality": {"gates": fail}}))
    assert qs.main([str(p)]) == 1
