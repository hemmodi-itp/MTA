import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.ui_execution.agent import UIExecutionAgent


class RunPlaywrightBaseUrlTests(unittest.TestCase):
    """The orchestrator resolves the active --module's URL onto request["url"]
    before dispatching to ui_execution — playwright.config.ts can't tell modules
    apart on its own (it only regex-scrapes the first `url:` in project.yaml),
    so _run_playwright must forward it as the BASE_URL env var Playwright reads."""

    @patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=True)
    @patch("agents.test_execution.ui_execution.agent._stream_proc")
    def test_base_url_forwarded_to_subprocess_env(self, mock_stream_proc, _mock_installed):
        mock_stream_proc.return_value = ("", "", False, 0)
        agent = UIExecutionAgent()

        agent._run_playwright(
            project_name="AWS_Test",
            safe="AWS_Test",
            scripts_dir="application_assets/projects/AWS_Test/test_creation/test_scripts",
            reports_dir="application_assets/projects/AWS_Test/test_execution/reports",
            ts_files=["test_M04_BS_001_example.spec.ts"],
            headless=True,
            base_url="https://aws.amazon.com/partners/",
        )

        env = mock_stream_proc.call_args.kwargs["env"]
        self.assertEqual(env["BASE_URL"], "https://aws.amazon.com/partners/")

    @patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=True)
    @patch("agents.test_execution.ui_execution.agent._stream_proc")
    def test_no_base_url_leaves_env_unset(self, mock_stream_proc, _mock_installed):
        mock_stream_proc.return_value = ("", "", False, 0)
        agent = UIExecutionAgent()

        agent._run_playwright(
            project_name="demo",
            safe="demo",
            scripts_dir="application_assets/projects/demo/test_creation/test_scripts",
            reports_dir="application_assets/projects/demo/test_execution/reports",
            ts_files=["test_BS-001_example.spec.ts"],
            headless=True,
        )

        env = mock_stream_proc.call_args.kwargs["env"]
        self.assertNotIn("BASE_URL", env)


if __name__ == "__main__":
    unittest.main()
