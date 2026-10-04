import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.ui_execution.agent import UIExecutionAgent, _find_scripts


class FindScriptsTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _touch(self, *parts):
        path = os.path.join(self.tmp_dir, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").close()

    def test_finds_specs_nested_under_module_subdirectories(self):
        self._touch("M01", "test_BS-001_login.spec.ts")
        self._touch("M02", "test_BS-010_sort.spec.ts")
        self._touch("M02", "test_BS-011_filter.spec.ts")

        found = _find_scripts(self.tmp_dir, ".spec.ts")

        self.assertEqual(
            sorted(f.replace(os.sep, "/") for f in found),
            ["M01/test_BS-001_login.spec.ts", "M02/test_BS-010_sort.spec.ts", "M02/test_BS-011_filter.spec.ts"],
        )

    def test_finds_specs_directly_in_scripts_dir_when_module_scoped(self):
        self._touch("test_BS-001_login.spec.ts")

        found = _find_scripts(self.tmp_dir, ".spec.ts")

        self.assertEqual(found, ["test_BS-001_login.spec.ts"])

    def test_returns_empty_list_when_nothing_matches(self):
        self._touch("M01", "README.md")

        self.assertEqual(_find_scripts(self.tmp_dir, ".spec.ts"), [])


class ExecuteDispatchesAcrossModulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_name = "test_discovery_project"
        self.scripts_dir = os.path.join(
            self.tmp_dir, self.project_name, "test_creation", "test_scripts"
        )
        os.makedirs(os.path.join(self.scripts_dir, "M01"))
        os.makedirs(os.path.join(self.scripts_dir, "M02"))
        open(os.path.join(self.scripts_dir, "M01", "test_BS-001_login.spec.ts"), "w").close()
        open(os.path.join(self.scripts_dir, "M02", "test_BS-010_sort.spec.ts"), "w").close()

        self.patcher = patch(
            "agents.test_execution.ui_execution.agent._ASSETS_BASE", self.tmp_dir
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch("agents.test_execution.ui_execution.agent.UIExecutionAgent._run_playwright")
    def test_no_module_filter_finds_specs_across_all_modules(self, mock_run_playwright):
        mock_run_playwright.return_value = {"module": "ui_execution", "status": "success"}

        agent = UIExecutionAgent()
        agent.execute({"project_name": self.project_name}, {})

        mock_run_playwright.assert_called_once()
        ts_files = mock_run_playwright.call_args.kwargs["ts_files"]
        self.assertEqual(len(ts_files), 2)

    @patch("agents.test_execution.ui_execution.agent.UIExecutionAgent._run_playwright")
    def test_module_filter_scopes_to_single_module(self, mock_run_playwright):
        mock_run_playwright.return_value = {"module": "ui_execution", "status": "success"}

        agent = UIExecutionAgent()
        agent.execute({"project_name": self.project_name, "module_filter": "M02"}, {})

        mock_run_playwright.assert_called_once()
        ts_files = mock_run_playwright.call_args.kwargs["ts_files"]
        self.assertEqual(ts_files, ["test_BS-010_sort.spec.ts"])


if __name__ == "__main__":
    unittest.main()
