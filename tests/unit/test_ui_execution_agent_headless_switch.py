import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.ui_execution.agent import UIExecutionAgent


def _browser_close_result(spec_file):
    return {
        "spec_file": spec_file,
        "test_title": "t",
        "status": "failed",
        "duration_ms": 100,
        "first_attempt_duration_ms": 100,  # < 5000ms => "no interaction"
        "errors": ["Target page, context or browser has been closed"],
        "comment": "",
        "no_interaction_close": False,
    }


class HeadlessSwitchWithNestedModulePathsTests(unittest.TestCase):
    """3 consecutive no-interaction browser closes in a headed run must switch
    remaining specs to headless — including when specs live under a module
    subdirectory (whole-project runs across multiple modules), not just when
    scripts_dir already points at a single module (--module scoped runs)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.scripts_dir = os.path.join(self.tmp_dir, "test_scripts")
        self.module_dir = os.path.join(self.scripts_dir, "M02")
        os.makedirs(self.module_dir)
        self.specs = [f"test_BS-{i:03d}_x.spec.ts" for i in range(1, 5)]
        for s in self.specs:
            open(os.path.join(self.module_dir, s), "w").close()

        self.reports_dir = os.path.join(self.tmp_dir, "reports")
        os.makedirs(os.path.join(self.reports_dir, "json"), exist_ok=True)
        os.makedirs(os.path.join(self.reports_dir, "html"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=True)
    @patch("agents.test_execution.ui_execution.agent._parse_playwright_json")
    @patch("agents.test_execution.ui_execution.agent._stream_proc")
    def test_actually_retries_remaining_specs_headless(self, mock_stream, mock_parse, _mock_installed):
        ts_files = [f"M02/{s}" for s in self.specs]
        first_run_results = (
            [_browser_close_result(f"M02/{s}") for s in self.specs[:3]]
            + [{
                "spec_file": f"M02/{self.specs[3]}", "test_title": "t", "status": "success",
                "duration_ms": 100, "first_attempt_duration_ms": 100, "errors": [],
                "comment": "", "no_interaction_close": False,
            }]
        )
        mock_stream.return_value = ("", "", False, 1)
        mock_parse.return_value = (first_run_results, 1, 3)

        agent = UIExecutionAgent()
        result = agent._run_playwright(
            project_name="demo", safe="demo",
            scripts_dir=self.scripts_dir, reports_dir=self.reports_dir,
            ts_files=ts_files, headless=False,
        )

        # The headed run + the headless retry — retry must actually fire, not no-op.
        self.assertEqual(mock_stream.call_count, 2)
        retry_cmd = mock_stream.call_args_list[1].kwargs.get("cmd") or mock_stream.call_args_list[1].args[0]
        self.assertTrue(any("M02" in part and "test_BS-004" in part for part in retry_cmd))

        by_spec = {r["spec_file"]: r for r in result["results"]}
        self.assertEqual(
            by_spec[f"M02/{self.specs[3]}"]["comment"],
            "Re-run headless after consecutive browser close(s)",
        )

    @patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=True)
    @patch("agents.test_execution.ui_execution.agent._parse_playwright_json")
    @patch("agents.test_execution.ui_execution.agent._stream_proc")
    def test_no_retry_when_fewer_than_three_consecutive_closes(self, mock_stream, mock_parse, _mock_installed):
        ts_files = [f"M02/{s}" for s in self.specs]
        results = (
            [_browser_close_result(f"M02/{s}") for s in self.specs[:2]]
            + [{
                "spec_file": f"M02/{s}", "test_title": "t", "status": "success",
                "duration_ms": 100, "first_attempt_duration_ms": 100, "errors": [],
                "comment": "", "no_interaction_close": False,
            } for s in self.specs[2:]]
        )
        mock_stream.return_value = ("", "", False, 1)
        mock_parse.return_value = (results, 2, 2)

        agent = UIExecutionAgent()
        agent._run_playwright(
            project_name="demo", safe="demo",
            scripts_dir=self.scripts_dir, reports_dir=self.reports_dir,
            ts_files=ts_files, headless=False,
        )

        # Only the original headed run — no retry triggered below the threshold.
        self.assertEqual(mock_stream.call_count, 1)


class HandleInterruptNestedPathTests(unittest.TestCase):
    """Specs not yet reached at interrupt time must be correctly identified as
    'not started' even when spec_file is a module-relative path, not a bare
    basename — completed_basenames is basename-keyed, so the comparison must
    normalize both sides consistently."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.reports_dir = os.path.join(self.tmp_dir, "reports")
        os.makedirs(os.path.join(self.reports_dir, "html", "run1"), exist_ok=True)
        self.json_report_path = os.path.join(self.tmp_dir, "results.json")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("agents.test_execution.ui_execution.agent._parse_playwright_json")
    def test_completed_nested_spec_is_not_marked_not_started(self, mock_parse):
        mock_parse.return_value = (
            [{
                "spec_file": "M02/test_BS-001_x.spec.ts", "test_title": "t", "status": "success",
                "duration_ms": 10, "errors": [], "comment": "", "first_attempt_duration_ms": 10,
                "no_interaction_close": False,
            }],
            1, 0,
        )

        agent = UIExecutionAgent()
        result = agent._handle_interrupt(
            ts_files=["M02/test_BS-001_x.spec.ts", "M02/test_BS-002_x.spec.ts"],
            scripts_dir="unused",
            json_report_path=self.json_report_path,
            reports_dir=self.reports_dir,
            html_report_dir=os.path.join(self.reports_dir, "html", "run1"),
            ts="run1",
            safe="demo",
            stdout="",
        )

        by_spec = {r["spec_file"]: r for r in result["results"]}
        self.assertEqual(by_spec["M02/test_BS-001_x.spec.ts"]["status"], "success")
        self.assertEqual(by_spec["M02/test_BS-002_x.spec.ts"]["status"], "skipped")
        self.assertEqual(by_spec["M02/test_BS-002_x.spec.ts"]["comment"], "Execution was interrupted before this test ran")


if __name__ == "__main__":
    unittest.main()
