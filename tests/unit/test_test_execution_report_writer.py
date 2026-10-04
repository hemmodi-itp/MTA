import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_execution.reports.report_writer import (
    build_report_dict, build_failure_summary, build_failures_log_text, _failure_signature,
)


class BuildReportDictExecutionShapeTests(unittest.TestCase):
    """Covers the two confirmed regressions: (1) report read outputs["execution"]
    only, but the default full_workflow pipeline populates outputs["ui_execution"];
    (2) per-row results assumed a nested result.steps[] shape UIExecutionAgent
    no longer produces — both silently zeroed every generated report."""

    def _build(self, outputs, execution_trace=None):
        return build_report_dict(
            project_name="proj",
            run_id="run-1",
            workflow="full_workflow",
            execution_trace=execution_trace or [],
            errors=[],
            outputs=outputs,
            generated_at=datetime.now(timezone.utc),
        )

    def test_ui_execution_key_populates_test_execution_report(self):
        outputs = {
            "ui_execution": {
                "module": "ui_execution",
                "status": "success",
                "passed": 1,
                "failed": 1,
                "scenarios_executed": 2,
                "results": [
                    {
                        "spec_file": "M02/test_BS-007_search.spec.ts",
                        "test_title": "search",
                        "test_case_id": "BS-007",
                        "business_scenario_id": "BS-007",
                        "status": "success",
                        "errors": [],
                    },
                    {
                        "spec_file": "M02/test_BS-011_filter.spec.ts",
                        "test_title": "filter",
                        "test_case_id": "BS-011",
                        "business_scenario_id": "BS-011",
                        "status": "failed",
                        "errors": ["Timeout"],
                    },
                ],
            }
        }
        report = self._build(outputs)
        ter = report["test_execution_report"]

        self.assertTrue(ter["executed"])
        self.assertEqual(ter["total"], 2)
        self.assertEqual(ter["passed"], 1)
        self.assertEqual(ter["failed"], 1)
        self.assertEqual(ter["pass_rate"], "50%")

        by_id = {r["test_case_id"]: r for r in ter["results"]}
        self.assertEqual(by_id["BS-007"]["status"], "success")
        self.assertEqual(by_id["BS-011"]["status"], "failed")
        self.assertNotEqual(by_id["BS-011"]["status"], "unknown")

    def test_legacy_execution_key_with_nested_summary_still_works(self):
        outputs = {
            "execution": {
                "module": "execution",
                "status": "success",
                "summary": {"scenarios_executed": 1, "passed": 1, "failed": 0},
                "results": [
                    {
                        "spec_file": "x.spec.ts",
                        "test_title": "x",
                        "test_case_id": "BS-001",
                        "business_scenario_id": "BS-001",
                        "status": "success",
                        "errors": [],
                    }
                ],
            }
        }
        report = self._build(outputs)
        ter = report["test_execution_report"]
        self.assertEqual(ter["total"], 1)
        self.assertEqual(ter["passed"], 1)

    def test_no_execution_output_yields_empty_not_error(self):
        report = self._build({})
        ter = report["test_execution_report"]
        self.assertFalse(ter["executed"])
        self.assertEqual(ter["results"], [])
        self.assertEqual(ter["pass_rate"], "N/A")

    def test_healing_artifacts_read_current_field_names(self):
        execution_trace = [{"step": "healing", "status": "success"}]
        outputs = {"healing": {"specs_healed": 2, "tests_healed": 5}}
        report = self._build(outputs, execution_trace)
        healing_entry = next(
            e for e in report["artifacts_generated"]["per_step"] if e["step"] == "healing"
        )
        self.assertEqual(healing_entry["artifacts"]["specs_healed"], 2)
        self.assertEqual(healing_entry["artifacts"]["tests_healed"], 5)

    def test_ui_execution_step_artifacts_not_none(self):
        execution_trace = [{"step": "ui_execution", "status": "success"}]
        outputs = {"ui_execution": {"passed": 3, "failed": 1, "scenarios_executed": 4}}
        report = self._build(outputs, execution_trace)
        step_entry = next(
            e for e in report["artifacts_generated"]["per_step"] if e["step"] == "ui_execution"
        )
        self.assertIsNotNone(step_entry["artifacts"])
        self.assertEqual(step_entry["artifacts"]["passed"], 3)


class HealingReportSectionTests(unittest.TestCase):
    """The new per-iteration healing_report section — reconstructed final
    tally from data, per the user's explicit four-tier request: raw result
    (before_healing), one entry per iteration (rounds), then the cumulative
    final result (final_result)."""

    def _build(self, outputs):
        return build_report_dict(
            project_name="proj", run_id="run-1", workflow="full_workflow",
            execution_trace=[], errors=[], outputs=outputs,
            generated_at=datetime.now(timezone.utc),
        )

    def test_healing_report_absent_when_no_healing_output(self):
        report = self._build({"ui_execution": {"passed": 1, "failed": 1, "scenarios_executed": 2}})
        self.assertIsNone(report["healing_report"])

    def test_healing_report_reconstructs_final_tally_from_remaining_count(self):
        # The user's own worked example: 12/20 originally, healing resolves
        # all but 2 of the 8 failures across however many rounds it took.
        outputs = {
            "ui_execution": {"passed": 12, "failed": 8, "scenarios_executed": 20},
            "healing": {
                "status": "partial",
                "rounds": [
                    {"round": 1, "spec_files": ["a"], "ran": True, "passed": 4, "failed": 4, "remaining_after": 4},
                    {"round": 2, "spec_files": ["b"], "ran": True, "passed": 2, "failed": 2, "remaining_after": 2},
                ],
                "remaining_failing_count": 2,
                "specs_healed": 2, "tests_healed": 6, "not_healable": [],
            },
        }
        report = self._build(outputs)
        hr = report["healing_report"]

        self.assertEqual(hr["before_healing"], {"passed": 12, "failed": 8, "total": 20})
        self.assertEqual(len(hr["rounds"]), 2)
        self.assertEqual(hr["rounds"][0]["passed"], 4)
        self.assertEqual(hr["rounds"][1]["passed"], 2)
        self.assertEqual(
            hr["final_result"],
            {"passed": 18, "failed": 2, "total": 20, "pass_rate": "90%"},
        )

    def test_healing_report_zero_rounds_falls_back_to_pre_healing_baseline(self):
        outputs = {
            "ui_execution": {"passed": 12, "failed": 8, "scenarios_executed": 20},
            "healing": {
                "status": "failed", "rounds": [], "specs_healed": 0,
                "tests_healed": 0, "not_healable": [],
                # remaining_failing_count absent -- crashed before any round ran
            },
        }
        report = self._build(outputs)
        hr = report["healing_report"]

        self.assertEqual(hr["rounds"], [])
        self.assertEqual(hr["final_result"], {**hr["before_healing"], "pass_rate": "60%"})
        self.assertEqual(hr["final_result"]["passed"], 12)
        self.assertEqual(hr["final_result"]["failed"], 8)

    def test_healing_report_does_not_use_tests_healed_for_final_tally(self):
        # tests_healed is deliberately inconsistent with remaining_failing_count
        # here -- the arithmetic must ignore it and use remaining_failing_count.
        outputs = {
            "ui_execution": {"passed": 14, "failed": 6, "scenarios_executed": 20},
            "healing": {
                "status": "partial", "rounds": [],
                "remaining_failing_count": 5,
                "specs_healed": 3, "tests_healed": 10,  # inflated/inconsistent on purpose
                "not_healable": [],
            },
        }
        report = self._build(outputs)
        final = report["healing_report"]["final_result"]
        # resolved = 6 - 5 = 1 -> final passed = 14 + 1 = 15, not derived from tests_healed=10
        self.assertEqual(final["passed"], 15)
        self.assertEqual(final["failed"], 5)

    def test_extract_step_artifacts_healing_branch_surfaces_new_fields(self):
        execution_trace = [{"step": "healing", "status": "success"}]
        outputs = {
            "healing": {
                "specs_healed": 2, "tests_healed": 5,
                "not_healable": [{"spec_file": "a", "test_name": "b", "reason": "real defect"}],
                "rounds": [{"round": 1}, {"round": 2}],
            }
        }
        report = build_report_dict(
            project_name="proj", run_id="run-1", workflow="full_workflow",
            execution_trace=execution_trace, errors=[], outputs=outputs,
            generated_at=datetime.now(timezone.utc),
        )
        healing_entry = next(
            e for e in report["artifacts_generated"]["per_step"] if e["step"] == "healing"
        )
        self.assertEqual(healing_entry["artifacts"]["not_healable_count"], 1)
        self.assertEqual(healing_entry["artifacts"]["rounds_run"], 2)


class FailureSignatureTests(unittest.TestCase):
    def test_extracts_locator_key_when_present(self):
        err = "Error: [locator_key=button_loc_0001_6] locator.fill: Error: Element is not an <input>"
        self.assertEqual(_failure_signature(err), "locator_key=button_loc_0001_6")

    def test_falls_back_to_first_line_when_no_locator_key(self):
        err = "Error: User should be on the Gemini landing page\n\nexpect(page).toHaveURL(expected) failed"
        self.assertEqual(_failure_signature(err), "Error: User should be on the Gemini landing page")

    def test_blank_error_yields_unknown(self):
        self.assertEqual(_failure_signature(""), "unknown error")


class BuildFailureSummaryTests(unittest.TestCase):
    """The real geminiTest report: 13 of 21 failures were all caused by the
    same wrong locator (button_loc_0001_6) but rendered as 13 separately
    scrolled raw stack traces with nothing tying them together. This groups
    failures by root cause so that's visible at a glance."""

    def test_groups_failures_sharing_a_locator_key(self):
        results = [
            {"test_case_id": "M01_BS_004", "status": "failed", "errors": ["[locator_key=button_loc_0001_6] fill error"]},
            {"test_case_id": "M01_BS_006", "status": "failed", "errors": ["[locator_key=button_loc_0001_6] fill error"]},
            {"test_case_id": "M01_BS_005", "status": "success", "errors": []},
        ]
        summary = build_failure_summary(results)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["signature"], "locator_key=button_loc_0001_6")
        self.assertEqual(summary[0]["count"], 2)
        self.assertEqual(set(summary[0]["test_case_ids"]), {"M01_BS_004", "M01_BS_006"})

    def test_distinct_causes_produce_distinct_groups_sorted_by_count(self):
        results = [
            {"test_case_id": "A", "status": "failed", "errors": ["[locator_key=x] boom"]},
            {"test_case_id": "B", "status": "failed", "errors": ["[locator_key=x] boom"]},
            {"test_case_id": "C", "status": "failed", "errors": ["[locator_key=x] boom"]},
            {"test_case_id": "D", "status": "failed", "errors": ["Error: some other assertion failed"]},
        ]
        summary = build_failure_summary(results)
        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["count"], 3)
        self.assertEqual(summary[1]["count"], 1)

    def test_passing_tests_are_excluded(self):
        results = [{"test_case_id": "A", "status": "success", "errors": []}]
        self.assertEqual(build_failure_summary(results), [])

    def test_failure_summary_present_in_full_report(self):
        outputs = {
            "ui_execution": {
                "passed": 0, "failed": 2, "scenarios_executed": 2,
                "results": [
                    {"test_case_id": "A", "test_title": "a", "business_scenario_id": "A", "status": "failed", "errors": ["[locator_key=x] boom"]},
                    {"test_case_id": "B", "test_title": "b", "business_scenario_id": "B", "status": "failed", "errors": ["[locator_key=x] boom"]},
                ],
            }
        }
        report = build_report_dict(
            project_name="proj", run_id="run-1", workflow="full_workflow",
            execution_trace=[], errors=[], outputs=outputs,
            generated_at=datetime.now(timezone.utc),
        )
        fs = report["test_execution_report"]["failure_summary"]
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["count"], 2)


class BuildFailuresLogTextTests(unittest.TestCase):
    def test_no_failures_reports_clean(self):
        report = {
            "project": "proj", "run_id": "r1", "generated_at": "now",
            "test_execution_report": {"passed": 3, "failed": 0, "total": 3, "pass_rate": "100%", "failure_summary": []},
        }
        text = build_failures_log_text(report)
        self.assertIn("No failures.", text)

    def test_lists_each_root_cause_with_affected_tests_and_example(self):
        report = {
            "project": "geminiTest", "run_id": "r1", "generated_at": "now",
            "test_execution_report": {
                "passed": 7, "failed": 21, "total": 28, "pass_rate": "25%",
                "failure_summary": [
                    {"signature": "locator_key=button_loc_0001_6", "count": 13,
                     "test_case_ids": ["M01_BS_004", "M01_BS_006"], "example_error": "fill error"},
                ],
            },
        }
        text = build_failures_log_text(report)
        self.assertIn("1 distinct root cause(s) behind 21 failure(s)", text)
        self.assertIn("13x — locator_key=button_loc_0001_6", text)
        self.assertIn("M01_BS_004, M01_BS_006", text)
        self.assertIn("fill error", text)


if __name__ == "__main__":
    unittest.main()
