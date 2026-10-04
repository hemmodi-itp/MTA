import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.execution.agent import ExecutionAgent


class ExtractFailuresFlatShapeTests(unittest.TestCase):
    """UIExecutionAgent's results are a flat list (no nested "result.steps[]") —
    _extract_failures must read that shape directly. Before this fix, every
    call here returned [] regardless of how many tests actually failed."""

    def setUp(self):
        self.agent = ExecutionAgent(settings={})

    def test_extracts_one_failure_per_error_on_failed_test(self):
        ui_result = {
            "results": [
                {
                    "spec_file": "M02/test_BS-007_search.spec.ts",
                    "test_case_id": "BS-007",
                    "business_scenario_id": "BS-007",
                    "status": "failed",
                    "errors": ["Timeout waiting for locator"],
                },
                {
                    "spec_file": "M02/test_BS-011_filter.spec.ts",
                    "test_case_id": "BS-011",
                    "business_scenario_id": "BS-011",
                    "status": "success",
                    "errors": [],
                },
            ]
        }

        failures = self.agent._extract_failures(ui_result)

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["test_case_id"], "BS-007")
        self.assertEqual(failures[0]["failure_reason"], "timeout_waiting_for_element")

    def test_no_failures_when_all_tests_succeed(self):
        ui_result = {"results": [{"spec_file": "x.spec.ts", "status": "success", "errors": []}]}
        self.assertEqual(self.agent._extract_failures(ui_result), [])

    def test_empty_errors_list_still_yields_one_generic_failure_entry(self):
        ui_result = {"results": [{"spec_file": "x.spec.ts", "status": "failed", "errors": []}]}
        failures = self.agent._extract_failures(ui_result)
        self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main()
