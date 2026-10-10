"""Phase 1.2 / 1.3 — UIExecutionAgent records Playwright's raw status, tags and annotations (tc / ac ids) per
result, and folds every run into traceability.json (a failure there never fails the run)."""

import json
import logging

from agents.test_execution.ui_execution import agent as ui

REPORT = {"suites": [{"specs": [
    {"file": "M01/test_M01_BS_002_failed_login.spec.ts", "title": "AC-01.2 negative — wrong password",
     "tags": ["P1", "negative", "regression", "REQ-01", "AC-01.2"],
     "tests": [{"status": "unexpected", "annotations": [
         {"type": "ac", "description": "AC-01.2"}, {"type": "tc", "description": "M01_TC_002"},
         {"type": "scenario", "description": "M01_BS_002"}],
         "results": [{"duration": 10, "error": {"message": "expected text"}}]}]},
    {"file": "M01/test_M01_BS_003.spec.ts", "title": "step 01 — stub", "tags": [],
     "tests": [{"status": "skipped", "annotations": [], "results": []}]},
    {"file": "M01/test_M01_BS_001.spec.ts", "title": "positive — legacy @smoke", "tags": ["smoke"],
     "tests": [{"status": "expected", "results": [{"duration": 5}]}]},
]}]}


def _parse(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps(REPORT), encoding="utf-8")
    return ui._parse_playwright_json(str(path), logging.getLogger("t"))


def test_tags_annotations_and_raw_status_are_recorded(tmp_path):
    results, passed, failed = _parse(tmp_path)
    traced, skipped, legacy = results
    assert traced["pw_status"] == "unexpected" and traced["status"] == "failed"
    assert traced["tc_id"] == "M01_TC_002" and traced["ac_ids"] == ["AC-01.2"]
    assert traced["tags"] == ["P1", "negative", "regression", "REQ-01", "AC-01.2"]
    assert {"type": "scenario", "description": "M01_BS_002"} in traced["annotations"]
    # existing behaviour is unchanged: Playwright "skipped" still counts as failed in `status` (design D6);
    # the raw status is kept beside it for traceability
    assert skipped["status"] == "failed" and skipped["pw_status"] == "skipped"
    assert (passed, failed) == (1, 2)
    assert "tc_id" not in legacy and legacy["annotations"] == [] and legacy["pw_status"] == "expected"


def test_apply_traceability_is_non_fatal(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr("tools.requirements.traceability.apply_results_for_project", boom)
    ui._apply_traceability("p", [{"tc_id": "x"}], "ts", logger=logging.getLogger("t"))   # must not raise


def test_apply_traceability_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    ui._apply_traceability("p", [{"tc_id": "x"}], "ts", logger=logging.getLogger("t"))
    assert not (tmp_path / "p" / "test_creation" / "traceability.json").exists()
