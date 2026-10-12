"""Phase 4.2 — the MTA reporter's output: contract, Python loader, and that traceability consumes it."""

import json

from contracts.artifacts.io import validate_document
from tools.execution.mta_results import load_mta_results, to_execution_results, totals
from tools.requirements.models import TraceabilityDoc
from tools.requirements.traceability import apply_results

DOC = {
    "schema_version": 2, "artifact": "mta_results", "run_id": "20261012T101010Z", "project": "shop",
    "shard": None, "started_at": "2026-10-12T10:10:10Z", "finished_at": "2026-10-12T10:11:10Z", "status": "failed",
    "totals": {"total": 3, "passed": 1, "failed": 1, "flaky": 1, "skipped": 0, "timedOut": 0, "interrupted": 0},
    "tests": [
        {"test_id": "a1", "title": "AC-01.1 valid login", "title_path": ["Login (M01_BS_001)", "AC-01.1 valid login"],
         "spec_file": "shop/test_creation/test_scripts/M01/test_M01_BS_001_login.spec.ts", "line": 9, "project": "chromium",
         "tags": ["@P0"], "annotations": [{"type": "ac", "description": "AC-01.1"}, {"type": "tc", "description": "M01_TC_001"}],
         "tc_id": "M01_TC_001", "case_id": None, "scenario_id": "M01_BS_001", "ac_ids": ["AC-01.1"],
         "status": "passed", "outcome": "expected", "expected_status": "passed", "retries": 0, "duration_ms": 900,
         "attempts": [{"retry": 0, "status": "passed", "duration_ms": 900, "error": None}], "attachments": []},
        {"test_id": "a2", "title": "AC-01.2 wrong password", "title_path": [], "spec_file": "shop/x.spec.ts",
         "project": "chromium", "tags": [], "annotations": [], "tc_id": "M01_TC_002", "ac_ids": ["AC-01.2"],
         "status": "flaky", "retries": 1, "duration_ms": 2000,
         "attempts": [{"retry": 0, "status": "failed", "duration_ms": 1000, "error": "boom"},
                      {"retry": 1, "status": "passed", "duration_ms": 1000, "error": None}],
         "attachments": [{"name": "trace", "content_type": "application/zip", "path": "/r/trace.zip"}]},
        {"test_id": "a3", "title": "timed out", "spec_file": "shop/y.spec.ts", "status": "timedOut",
         "attempts": [{"retry": 0, "status": "timedOut", "duration_ms": 60000, "error": "Test timeout"}]},
    ],
}


def test_contract_accepts_the_reporter_shape():
    assert validate_document("mta_results", DOC).ok


def test_contract_rejects_an_unknown_status():
    bad = json.loads(json.dumps(DOC))
    bad["tests"][0]["status"] = "green"
    report = validate_document("mta_results", bad)
    assert not report.ok and "status" in report.errors[0]


def test_loader_reads_and_rejects(tmp_path):
    p = tmp_path / "x.mta_results.json"
    p.write_text(json.dumps(DOC), encoding="utf-8")
    assert load_mta_results(str(p))["run_id"] == "20261012T101010Z"
    assert load_mta_results(str(tmp_path / "missing.json")) is None
    (tmp_path / "junk.json").write_text("{not json", encoding="utf-8")
    assert load_mta_results(str(tmp_path / "junk.json")) is None
    (tmp_path / "other.json").write_text(json.dumps({"artifact": "execution_results"}), encoding="utf-8")
    assert load_mta_results(str(tmp_path / "other.json")) is None


def test_conversion_to_execution_results_shape():
    rows = to_execution_results(DOC)
    assert [r["status"] for r in rows] == ["success", "flaky", "failed"]   # flaky is never turned into a pass
    assert [r["pw_status"] for r in rows] == ["passed", "flaky", "timedOut"]
    assert rows[0]["tc_id"] == "M01_TC_001" and rows[0]["ac_ids"] == ["AC-01.1"]
    assert rows[1]["flaky"] is True and rows[1]["errors"] == ["boom"]
    assert rows[1]["first_attempt_duration_ms"] == 1000
    assert rows[1]["attachments"][0]["path"] == "/r/trace.zip"
    assert to_execution_results(None) == []


def test_totals():
    assert totals(DOC)["flaky"] == 1 and totals(None)["total"] == 0


def _trace_doc():
    return TraceabilityDoc.model_validate({
        "acs": {"AC-01.1": {"tc_ids": ["M01_TC_001"]}, "AC-01.2": {"tc_ids": ["M01_TC_002"]}},
        "tests": {"M01_TC_001": {"ac_ids": ["AC-01.1"], "spec_file": "M01/test_M01_BS_001_login.spec.ts",
                                 "test_title": "AC-01.1 valid login"},
                  "M01_TC_002": {"ac_ids": ["AC-01.2"]}},
    })


def test_traceability_consumes_the_loader_output():
    trace, unmatched = apply_results(_trace_doc(), to_execution_results(DOC), run="r1")
    assert unmatched == 1                                   # the timed-out test has no tc_id
    assert trace.tests["M01_TC_001"].latest_result.status == "passed"
    assert trace.tests["M01_TC_002"].latest_result.pw_status == "flaky"
