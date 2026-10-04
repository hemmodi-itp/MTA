import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.ui_execution.agent import UIExecutionAgent


class PlaywrightPackageMissingTests(unittest.TestCase):
    @patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=False)
    @patch("agents.test_execution.ui_execution.agent._stream_proc")
    def test_run_playwright_fails_fast_without_installing(self, mock_stream_proc, _mock_installed):
        agent = UIExecutionAgent()

        result = agent._run_playwright(
            project_name="demo",
            safe="demo",
            scripts_dir="application_assets/projects/demo/test_creation/test_scripts",
            reports_dir="application_assets/projects/demo/test_execution/reports",
            ts_files=["test_BS-001_example.spec.ts"],
            headless=True,
        )

        self.assertEqual(result["module"], "ui_execution")
        self.assertEqual(result["status"], "failed")
        self.assertIn("npm install", result["error"])
        mock_stream_proc.assert_not_called()


class ChromiumBinaryMissingTests(unittest.TestCase):
    @patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=True)
    @patch("agents.test_execution.ui_execution.agent._stream_proc")
    def test_run_playwright_fails_fast_without_reinstalling_browser(self, mock_stream_proc, _mock_installed):
        mock_stream_proc.return_value = (
            "",
            "browserType.launch: Executable doesn't exist at ...\\chromium-1234\\chrome.exe",
            False,
            1,
        )

        agent = UIExecutionAgent()
        result = agent._run_playwright(
            project_name="demo",
            safe="demo",
            scripts_dir="application_assets/projects/demo/test_creation/test_scripts",
            reports_dir="application_assets/projects/demo/test_execution/reports",
            ts_files=["test_BS-001_example.spec.ts"],
            headless=True,
        )

        self.assertEqual(result["module"], "ui_execution")
        self.assertEqual(result["status"], "failed")
        self.assertIn("playwright install chromium", result["error"])
        # No retry attempt — the process should only be invoked once.
        mock_stream_proc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
