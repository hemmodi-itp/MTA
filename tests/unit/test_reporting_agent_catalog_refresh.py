import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import agents.test_execution.reporting.agent as reporting_agent_module
from agents.test_execution.reporting.agent import ReportingAgent
from tools.catalog import catalog_manager


class ReportingAgentCatalogRefreshTests(unittest.TestCase):
    """ReportingAgent runs unconditionally right after ui_execution/healing —
    it's the one place guaranteed to see real per-test results, so it's
    responsible for stamping last_result/last_run back onto test_suite.json
    and refreshing the human-readable catalog. Before this fix, nothing in
    the pipeline ever did either, so the catalog stayed permanently blank."""

    def setUp(self):
        self.tmp_base = tempfile.mkdtemp()
        self._orig_reporting_base = reporting_agent_module._ASSETS_BASE
        self._orig_catalog_base = catalog_manager._ASSETS_BASE
        reporting_agent_module._ASSETS_BASE = self.tmp_base
        catalog_manager._ASSETS_BASE = self.tmp_base

        self.project_name = "demo_project"
        self.project_dir = os.path.join(self.tmp_base, self.project_name)
        suite_path = os.path.join(self.project_dir, "test_creation", "test_suite.json")
        os.makedirs(os.path.dirname(suite_path), exist_ok=True)
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump({"specs": [
                {"spec_id": "M03_BS_006", "file": "M03/test_M03_BS_006.spec.ts",
                 "last_result": None, "last_run": None},
            ]}, f)
        self.suite_path = suite_path

        scenarios_path = os.path.join(self.project_dir, "test_comprehension", "business_scenarios.json")
        os.makedirs(os.path.dirname(scenarios_path), exist_ok=True)
        with open(scenarios_path, "w", encoding="utf-8") as f:
            json.dump({"scenarios": [
                {"scenario_id": "M03_BS_006", "title": "Verify page title", "module_id": "M03"},
            ]}, f)

    def tearDown(self):
        reporting_agent_module._ASSETS_BASE = self._orig_reporting_base
        catalog_manager._ASSETS_BASE = self._orig_catalog_base
        shutil.rmtree(self.tmp_base, ignore_errors=True)

    def test_real_ui_execution_result_is_stamped_and_catalog_refreshed(self):
        agent = ReportingAgent()
        state = {
            "run_id": "run-1",
            "outputs": {
                "ui_execution": {
                    "status": "success",
                    "passed": 1,
                    "failed": 0,
                    "scenarios_executed": 1,
                    "results": [{
                        "spec_file": "M03/test_M03_BS_006.spec.ts",
                        "test_case_id": "M03_BS_006",
                        "business_scenario_id": "M03_BS_006",
                        "status": "success",
                        "errors": [],
                    }],
                },
            },
        }

        result = agent.execute({"project_name": self.project_name}, state)

        with open(self.suite_path, encoding="utf-8") as f:
            suite = json.load(f)
        self.assertEqual(suite["specs"][0]["last_result"], "passed")
        self.assertIsNotNone(suite["specs"][0]["last_run"])

        catalog_md = os.path.join(self.project_dir, "test_creation", "test_catalog.md")
        self.assertTrue(os.path.exists(catalog_md))
        with open(catalog_md, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("passed", content)

        # A clean, all-passing run still writes a failures log — "No failures."
        failures_path = result["failures_log_path"]
        self.assertTrue(os.path.exists(failures_path))
        with open(failures_path, encoding="utf-8") as f:
            self.assertIn("No failures.", f.read())

    def test_no_results_means_no_catalog_write_attempted(self):
        agent = ReportingAgent()
        state = {"run_id": "run-1", "outputs": {}}

        agent.execute({"project_name": self.project_name}, state)

        with open(self.suite_path, encoding="utf-8") as f:
            suite = json.load(f)
        # Untouched — no execution results means nothing to stamp.
        self.assertIsNone(suite["specs"][0]["last_result"])


if __name__ == "__main__":
    unittest.main()
