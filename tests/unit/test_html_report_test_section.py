import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_execution.reports.html_report import _test_section


class TestSectionErrorRenderingTests(unittest.TestCase):
    """ui_execution results have no "steps" shape (that belongs to the legacy
    ExecutionAgent) — _test_section used to silently drop the flat "errors"
    list report_writer.py already preserves, always rendering "No step
    details available" for every failed ui_execution test."""

    def test_renders_flat_errors_list_when_no_steps_present(self):
        ter = {
            "executed": True,
            "total": 1,
            "passed": 0,
            "failed": 1,
            "results": [{
                "test_case_id": "M03_BS_006",
                "test_case_name": "verify page title",
                "business_scenario_id": "M03_BS_006",
                "status": "failed",
                "errors": ["Timeout waiting for locator 'page.getByRole(...)'"],
            }],
        }

        html = _test_section(ter)

        self.assertIn("Timeout waiting for locator", html)
        self.assertNotIn("No step details available", html)

    def test_falls_back_to_no_details_when_neither_steps_nor_errors_present(self):
        ter = {
            "executed": True,
            "total": 1,
            "passed": 1,
            "failed": 0,
            "results": [{
                "test_case_id": "M03_BS_005",
                "test_case_name": "passing test",
                "business_scenario_id": "M03_BS_005",
                "status": "success",
                "errors": [],
            }],
        }

        html = _test_section(ter)

        self.assertIn("No step details available", html)

    def test_legacy_steps_shape_still_takes_priority_over_errors(self):
        ter = {
            "executed": True,
            "total": 1,
            "passed": 0,
            "failed": 1,
            "results": [{
                "test_case_id": "BS-001",
                "test_case_name": "legacy",
                "business_scenario_id": "BS-001",
                "status": "failed",
                "errors": ["should not appear"],
                "steps": [{
                    "step_id": "1", "action": "click", "status": "failed",
                    "locator_id": "LOC-0001", "details": {"error": "step-level error"},
                }],
            }],
        }

        html = _test_section(ter)

        self.assertIn("step-level error", html)
        self.assertNotIn("should not appear", html)


class FailureSummarySectionTests(unittest.TestCase):
    def test_renders_grouped_failure_counts_and_affected_tests(self):
        ter = {
            "executed": True,
            "total": 2,
            "passed": 0,
            "failed": 2,
            "results": [
                {"test_case_id": "A", "status": "failed", "errors": ["[locator_key=x] boom"]},
                {"test_case_id": "B", "status": "failed", "errors": ["[locator_key=x] boom"]},
            ],
            "failure_summary": [
                {"signature": "locator_key=x", "count": 2, "test_case_ids": ["A", "B"], "example_error": "[locator_key=x] boom"},
            ],
        }

        html = _test_section(ter)

        self.assertIn("Failure Summary", html)
        self.assertIn("locator_key=x", html)
        self.assertIn("2×", html)
        self.assertIn("A, B", html)

    def test_no_section_rendered_when_failure_summary_is_empty(self):
        ter = {"executed": True, "total": 1, "passed": 1, "failed": 0, "results": [], "failure_summary": []}
        html = _test_section(ter)
        self.assertNotIn("Failure Summary", html)


if __name__ == "__main__":
    unittest.main()
