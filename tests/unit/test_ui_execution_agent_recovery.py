import logging
import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.ui_execution.agent import _recover_partial_results, _stream_proc


class StreamProcNoTimeoutByDefaultTests(unittest.TestCase):
    """No outer timeout is applied unless a caller explicitly opts in — the
    hardcoded 900s suite-level kill that used to discard real, already-
    completed results has been removed."""

    def test_completes_normally_without_a_timeout_kwarg(self):
        logger = logging.getLogger("test")
        stdout, _stderr, interrupted, rc = _stream_proc(
            [sys.executable, "-c", "print('hello')"],
            cwd=os.getcwd(),
            env=os.environ.copy(),
            logger=logger,
        )
        self.assertFalse(interrupted)
        self.assertEqual(rc, 0)
        self.assertIn("hello", stdout)

    def test_explicit_timeout_still_kills_and_marks_interrupted(self):
        logger = logging.getLogger("test")
        stdout, _stderr, interrupted, rc = _stream_proc(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=os.getcwd(),
            env=os.environ.copy(),
            logger=logger,
            timeout=1,
        )
        self.assertTrue(interrupted)
        self.assertNotEqual(rc, 0)


class RecoverPartialResultsTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test")

    @patch("agents.test_execution.ui_execution.agent._parse_playwright_json")
    def test_prefers_json_report_when_present(self, mock_parse):
        mock_parse.return_value = (
            [{"spec_file": "M03/test_a.spec.ts", "status": "success",
              "errors": [], "comment": "", "first_attempt_duration_ms": 10,
              "no_interaction_close": False}],
            1, 0,
        )

        results = _recover_partial_results(
            ts_files=["M03/test_a.spec.ts", "M03/test_b.spec.ts"],
            json_report_path="unused.json",
            stdout="",
            logger=self.logger,
        )

        by_spec = {r["spec_file"]: r for r in results}
        self.assertEqual(by_spec["M03/test_a.spec.ts"]["status"], "success")
        # Never reached — marked skipped, not fabricated as failed.
        self.assertEqual(by_spec["M03/test_b.spec.ts"]["status"], "skipped")

    @patch("agents.test_execution.ui_execution.agent._parse_playwright_json")
    def test_falls_back_to_stdout_list_output_when_json_missing(self, mock_parse):
        mock_parse.return_value = ([], 0, 0)
        stdout = (
            "  ✓   1 [chromium] › M03/test_a.spec.ts › suite › case a (1.0s)\n"
            "  ✘   2 [chromium] › M03/test_b.spec.ts › suite › case b (1.0s)\n"
        )

        results = _recover_partial_results(
            ts_files=["M03/test_a.spec.ts", "M03/test_b.spec.ts", "M03/test_c.spec.ts"],
            json_report_path="unused.json",
            stdout=stdout,
            logger=self.logger,
        )

        by_spec = {r["spec_file"]: r for r in results}
        self.assertEqual(by_spec["test_a.spec.ts"]["status"], "success")
        self.assertEqual(by_spec["test_b.spec.ts"]["status"], "failed")
        # Never printed a result line at all — genuinely not started.
        self.assertEqual(by_spec["M03/test_c.spec.ts"]["status"], "skipped")
        self.assertEqual(
            by_spec["M03/test_c.spec.ts"]["comment"],
            "Execution was interrupted before this test ran",
        )

    @patch("agents.test_execution.ui_execution.agent._parse_playwright_json")
    def test_nothing_ran_at_all_marks_every_spec_skipped_not_failed(self, mock_parse):
        mock_parse.return_value = ([], 0, 0)

        results = _recover_partial_results(
            ts_files=["M03/test_a.spec.ts"],
            json_report_path="unused.json",
            stdout="",
            logger=self.logger,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
