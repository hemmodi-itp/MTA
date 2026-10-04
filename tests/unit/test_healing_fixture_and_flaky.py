import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.healing.tools import HealingRunContext, _get_failing_tests, _propose_fixture_fix


class GetFailingTestsFlakyExclusionTests(unittest.TestCase):
    """The real geminiTest bug: a test that failed its first attempt but
    passed on Playwright's automatic retry gets status "flaky" — Playwright's
    own summary counts this as a pass. HealingAgent used to treat it as a
    failure needing repair, wasting a cycle (and risking patching a
    perfectly fine locator) on a test that already recovered on its own."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.report_path = os.path.join(self.tmp_dir, "results.json")
        self.logger = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write(self, report):
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump(report, f)

    def test_flaky_status_is_not_reported_as_failing(self):
        self._write({"suites": [{"specs": [{
            "file": "application_assets/projects/proj/test_creation/test_scripts/M01/test_x.spec.ts",
            "title": "model select",
            "tests": [{"status": "flaky"}],
        }]}]})
        failing = _get_failing_tests(self.report_path, self.logger)
        self.assertEqual(failing, {})

    def test_truly_failed_status_is_still_reported(self):
        self._write({"suites": [{"specs": [{
            "file": "application_assets/projects/proj/test_creation/test_scripts/M01/test_x.spec.ts",
            "title": "model select",
            "tests": [{"status": "failed"}],
        }]}]})
        failing = _get_failing_tests(self.report_path, self.logger)
        self.assertEqual(failing, {"M01/test_x.spec.ts": ["model select"]})

    def test_passed_and_expected_still_excluded_as_before(self):
        self._write({"suites": [{"specs": [{
            "file": "application_assets/projects/proj/test_creation/test_scripts/M01/test_x.spec.ts",
            "title": "a",
            "tests": [{"status": "passed"}],
        }, {
            "file": "M01/test_y.spec.ts",
            "title": "b",
            "tests": [{"status": "expected"}],
        }]}]})
        failing = _get_failing_tests(self.report_path, self.logger)
        self.assertEqual(failing, {})


class ProposeFixtureFixTests(unittest.TestCase):
    """The real geminiTest bug: 5 of 21 failures were ENOENT errors from
    ActionEngine.uploadFile() referencing file names TestDataAgent invented
    but never created on disk — a test-data gap, not a locator bug, even
    though the error is tagged [locator_key=...] like every other
    ActionEngine failure and could mislead propose_locator_fix into trying
    (and failing) to re-scan a perfectly fine locator."""

    def _ctx(self, remaining):
        ctx = HealingRunContext(
            project_name="proj", scripts_dir="", reports_dir="", report_json="",
            dom_elements=[], module_urls={}, default_url="", test_data_map={},
            settings={}, logger=MagicMock(),
        )
        ctx.remaining = remaining
        return ctx

    def test_detects_enoent_signature(self):
        ctx = self._ctx({})
        ctx.remaining = {"M01/test_x.spec.ts": {
            "t1": "Error: [locator_key=button_loc_0001_6] ENOENT: no such file or directory, "
                  "stat 'C:\\Projects\\agentic-qa-platform\\sample_document.pdf'",
        }}
        result = _propose_fixture_fix(ctx, "M01/test_x.spec.ts", "t1")
        self.assertTrue(result["is_fixture_issue"])
        self.assertEqual(result["missing_file"], "C:\\Projects\\agentic-qa-platform\\sample_document.pdf")
        self.assertIn("mark_not_healable", result["reason"])

    def test_detects_actionengine_upload_fixture_not_found_message(self):
        ctx = self._ctx({})
        ctx.remaining = {"M01/test_x.spec.ts": {
            "t1": "Error: [locator_key=button_loc_0001_6] Upload fixture not found: "
                  "'malware_file.exe'. TestDataAgent referenced this file name but never "
                  "generated it on disk.",
        }}
        result = _propose_fixture_fix(ctx, "M01/test_x.spec.ts", "t1")
        self.assertTrue(result["is_fixture_issue"])
        self.assertEqual(result["missing_file"], "malware_file.exe")

    def test_non_fixture_error_is_not_flagged(self):
        ctx = self._ctx({})
        ctx.remaining = {"M01/test_x.spec.ts": {
            "t1": "Error: [locator_key=sign_in] locator.click: strict mode violation: "
                  "resolved to 2 elements",
        }}
        result = _propose_fixture_fix(ctx, "M01/test_x.spec.ts", "t1")
        self.assertFalse(result["is_fixture_issue"])

    def test_unknown_test_yields_not_a_fixture_issue(self):
        ctx = self._ctx({})
        ctx.remaining = {}
        result = _propose_fixture_fix(ctx, "M01/test_x.spec.ts", "missing")
        self.assertFalse(result["is_fixture_issue"])


if __name__ == "__main__":
    unittest.main()
