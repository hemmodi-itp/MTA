import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_execution.reports.html_report import _healing_section, build_html_report


class HealingSectionRenderingTests(unittest.TestCase):
    def test_returns_empty_string_when_healing_report_is_none(self):
        self.assertEqual(_healing_section(None), "")
        self.assertEqual(_healing_section({}), "")

    def test_renders_one_block_per_round_with_pass_fail_counts(self):
        hr = {
            "rounds": [
                {"round": 1, "spec_files": ["a.spec.ts"], "ran": True, "passed": 4, "failed": 4, "remaining_after": 4},
                {"round": 2, "spec_files": ["b.spec.ts"], "ran": True, "passed": 2, "failed": 2, "remaining_after": 2},
            ],
            "not_healable": [],
            "final_result": {"passed": 18, "failed": 2, "total": 20, "pass_rate": "90%"},
        }
        html = _healing_section(hr)

        self.assertIn("Round 1", html)
        self.assertIn("Round 2", html)
        self.assertIn("a.spec.ts", html)
        self.assertIn("b.spec.ts", html)
        self.assertIn(">4<", html)
        self.assertIn(">2<", html)

    def test_renders_final_result_stat_block(self):
        hr = {
            "rounds": [],
            "not_healable": [],
            "final_result": {"passed": 18, "failed": 2, "total": 20, "pass_rate": "90%"},
        }
        html = _healing_section(hr)

        self.assertIn(">18<", html)
        self.assertIn("Final Passed", html)
        self.assertIn("Final Failed", html)
        self.assertIn("90%", html)

    def test_renders_not_healable_reasons(self):
        hr = {
            "rounds": [],
            "not_healable": [
                {"spec_file": "M03/test_x.spec.ts", "test_name": "positive flow", "reason": "real app defect"},
            ],
            "final_result": {"passed": 0, "failed": 1, "total": 1, "pass_rate": "0%"},
        }
        html = _healing_section(hr)

        self.assertIn("M03/test_x.spec.ts", html)
        self.assertIn("positive flow", html)
        self.assertIn("real app defect", html)

    def test_round_with_ran_false_renders_error_not_pass_fail_stats(self):
        hr = {
            "rounds": [
                {"round": 1, "spec_files": ["a.spec.ts"], "ran": False, "error": "playwright not installed"},
            ],
            "not_healable": [],
            "final_result": {"passed": 0, "failed": 1, "total": 1, "pass_rate": "0%"},
        }
        html = _healing_section(hr)

        self.assertIn("playwright not installed", html)
        self.assertNotIn("Still Failing", html)

    def test_build_html_report_renumbers_errors_section_to_five(self):
        report = {
            "project": "proj",
            "workflow_status": {"steps": []},
            "artifacts_generated": {"summary": {}, "per_step": []},
            "test_execution_report": {"executed": False},
            "healing_report": {
                "rounds": [], "not_healable": [],
                "final_result": {"passed": 0, "failed": 0, "total": 0, "pass_rate": "N/A"},
            },
            "errors_and_validation": {"errors": [], "warnings": []},
        }
        html = build_html_report(report)

        self.assertIn("5. Errors", html)
        self.assertNotIn("4. Errors", html)
        self.assertIn("Healing Report", html)


if __name__ == "__main__":
    unittest.main()
