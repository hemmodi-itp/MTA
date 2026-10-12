"""Phase 4.7 — "flaky" (failed, then passed on a retry) is never recorded as "passed" by the consumers of
UIExecution results: traceability.json, test_suite.json, the ReportingAgent JSON/HTML and the benchmark scorer."""

import json
import os

from tools.benchmark.score import FLAKY, PASS, detect_bugs, flaky_tests, normalize_status, score
from tools.catalog.catalog_manager import stamp_execution_results
from tools.requirements.models import LatestResult
from tools.requirements.traceability import _aggregate_result, result_status
from tools.test_execution.reports.html_report import build_html_report
from tools.test_execution.reports.report_writer import build_report_dict


# ── traceability ─────────────────────────────────────────────────────────────

def test_traceability_result_status_keeps_flaky():
    assert result_status({"pw_status": "flaky", "status": "flaky"}) == "flaky"
    assert result_status({"status": "flaky"}) == "flaky"
    assert result_status({"pw_status": "expected"}) == "passed"
    assert LatestResult(status="flaky").status == "flaky"


def test_ac_aggregation_with_flaky():
    assert _aggregate_result(["passed", "flaky"]) == "flaky"
    assert _aggregate_result(["flaky"]) == "flaky"
    assert _aggregate_result(["flaky", "failed"]) == "mixed"
    assert _aggregate_result(["failed"]) == "failed"
    assert _aggregate_result(["passed"]) == "passed"


# ── test_suite.json ──────────────────────────────────────────────────────────

def _suite(tmp_path, ids):
    tc = tmp_path / "test_creation"
    tc.mkdir()
    (tc / "test_suite.json").write_text(json.dumps({"specs": [{"spec_id": i, "file": f"{i}.spec.ts"} for i in ids]}))
    return tc / "test_suite.json"


def test_suite_stamp_records_flaky_and_skipped_and_the_worst_test_wins(tmp_path):
    path = _suite(tmp_path, ["M01_BS_001", "M01_BS_002", "M01_BS_003", "M01_BS_004"])
    stamp_execution_results(str(tmp_path), [
        {"business_scenario_id": "M01_BS_001", "status": "flaky"},
        {"business_scenario_id": "M01_BS_002", "status": "success"},
        {"business_scenario_id": "M01_BS_002", "status": "flaky"},
        {"business_scenario_id": "M01_BS_002", "status": "success"},     # a later pass doesn't hide the flaky one
        {"business_scenario_id": "M01_BS_003", "status": "skipped"},
        {"business_scenario_id": "M01_BS_004", "status": "failed"},
        {"business_scenario_id": "M01_BS_004", "status": "flaky"},
    ])
    last = {s["spec_id"]: s["last_result"] for s in json.loads(path.read_text())["specs"]}
    assert last == {"M01_BS_001": "flaky", "M01_BS_002": "flaky", "M01_BS_003": "skipped", "M01_BS_004": "failed"}


# ── ReportingAgent JSON + HTML ───────────────────────────────────────────────

def test_report_json_and_html_show_flaky_and_skipped():
    from datetime import datetime, timezone
    outputs = {"ui_execution": {"passed": 1, "flaky": 1, "failed": 1, "skipped": 1, "scenarios_executed": 4, "results": [
        {"test_title": "a", "status": "success"}, {"test_title": "b", "status": "flaky", "flaky": True},
        {"test_title": "c", "status": "failed", "errors": ["boom"]}, {"test_title": "d", "status": "skipped"}]}}
    rep = build_report_dict("shop", "run1", "wf", [{"step": "ui_execution", "status": "success"}], [], outputs,
                            datetime.now(timezone.utc))
    ter = rep["test_execution_report"]
    assert (ter["passed"], ter["flaky"], ter["failed"], ter["skipped"], ter["pass_rate"]) == (1, 1, 1, 1, "25%")
    assert [r["status"] for r in ter["results"]] == ["success", "flaky", "failed", "skipped"]
    html = build_html_report(rep)
    assert "chip-flaky" in html and ">FLAKY<" in html and "⚠ Flaky" in html and "○ Skipped" in html
    assert "1 flaky" in html


# ── benchmark scorer ─────────────────────────────────────────────────────────

def test_scorer_flaky_is_never_a_pass_a_catch_or_a_false_failure():
    assert normalize_status("flaky") == FLAKY and normalize_status("success") == PASS
    clean = [{"t1": "passed", "t2": "flaky", "t3": "failed"}, {"t1": "passed", "t2": "passed", "t3": "failed"}]
    bugs = {"BUG_X": {"t1": "flaky", "t2": "failed", "t3": "failed"}}
    assert detect_bugs(clean, bugs) == {"BUG_X": []}            # t1 flaky in the bug run; t2 not a stable pass
    assert flaky_tests(clean) == ["t2"]
    assert flaky_tests([{"t1": "flaky", "t2": "passed"}]) == ["t1"]      # one run with retries is enough
    assert flaky_tests([{"t1": "passed"}]) is None
    m = score({"app": "x", "tests": [{"id": t} for t in ("t1", "t2", "t3")], "clean_runs": clean, "bug_runs": bugs},
              bugs=[{"id": "BUG_X"}], acs=[], pricing={})
    assert m["tests_executed"] == 3
    assert m["false_failure"]["failing_tests"] == ["t3"]
    assert m["flaky"]["tests"] == ["t2"]
    assert m["seeded_bug_detection"]["caught"] == 0
