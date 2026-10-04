import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.comprehension.comprehension_agent.agent import ComprehensionAgent


class _FakeDoc:
    file_name = "fake.md"


class _FakeScenario:
    def __init__(self, scenario_id):
        self.scenario_id = scenario_id


class ExecuteModularIncrementalExportTests(unittest.TestCase):
    """A multi-module BRD comprehension run must persist each module's
    scenarios to disk as soon as that module finishes, not only once at the
    very end — otherwise a caller-side timeout that abandons the run
    partway through the loop loses every module that had already completed.
    See DiscoveryAgent._promote_comprehension_partial, which relies on this
    per-module write actually happening."""

    def setUp(self):
        self.agent = ComprehensionAgent(settings={})
        self.modules = [
            {"id": "M01", "name": "Homepage"},
            {"id": "M02", "name": "Checkout"},
        ]

    def _run(self, parse_side_effect, generate_side_effect, validate_side_effect):
        with patch(
            "agents.comprehension.comprehension_agent.agent.parse_all_documents",
            side_effect=parse_side_effect,
        ), patch(
            "agents.comprehension.comprehension_agent.agent.extract_requirements",
            return_value={"requirements": [], "business_rules": [], "actors": [], "workflows": []},
        ), patch(
            "agents.comprehension.comprehension_agent.agent.generate_business_scenarios",
            side_effect=generate_side_effect,
        ), patch(
            "agents.comprehension.comprehension_agent.agent.validate_business_scenarios",
            side_effect=validate_side_effect,
        ), patch(
            "agents.comprehension.comprehension_agent.agent.export_scenarios",
            return_value={"json": "fake.json", "markdown": "fake.md"},
        ) as mock_export, patch(
            "agents.comprehension.comprehension_agent.agent.load_existing_titles_by_module",
            return_value={},
        ):
            result = self.agent._execute_modular(
                request={}, project_name="proj", input_dir="in", output_dir="out",
                modules=self.modules, llm=None, artifact_registry=_NoopRegistry(),
            )
        return result, mock_export

    def test_each_successful_module_is_exported_immediately(self):
        m01_scenario = _FakeScenario("M01-SC-001")
        m02_scenario = _FakeScenario("M02-SC-001")

        result, mock_export = self._run(
            parse_side_effect=[[_FakeDoc()], [_FakeDoc()]],
            generate_side_effect=[[m01_scenario], [m02_scenario]],
            validate_side_effect=[([m01_scenario], []), ([m02_scenario], [])],
        )

        self.assertEqual(result["status"], "success")
        self.assertNotIn("skipped_modules", result)

        # 2 per-module checkpoint exports + 1 final combined export.
        self.assertEqual(mock_export.call_count, 3)
        first_call_scenarios, _, _ = mock_export.call_args_list[0][0]
        self.assertEqual(first_call_scenarios, [m01_scenario])
        self.assertEqual(mock_export.call_args_list[0][1]["module_ids"], ["M01"])
        second_call_scenarios, _, _ = mock_export.call_args_list[1][0]
        self.assertEqual(second_call_scenarios, [m02_scenario])
        self.assertEqual(mock_export.call_args_list[1][1]["module_ids"], ["M02"])

    def test_module_with_no_documents_is_skipped_and_status_is_partial(self):
        m01_scenario = _FakeScenario("M01-SC-001")

        result, mock_export = self._run(
            parse_side_effect=[[_FakeDoc()], []],  # M02 parses to nothing
            generate_side_effect=[[m01_scenario]],
            validate_side_effect=[([m01_scenario], [])],
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["scenarios_valid"], 1)
        self.assertEqual(
            result["skipped_modules"],
            [{"module_id": "M02", "reason": "no documents parsed"}],
        )
        self.assertIn("M02", result["error"])

        # Only M01 ever gets to export_scenarios: one incremental + one final.
        self.assertEqual(mock_export.call_count, 2)

    def test_all_modules_skipped_reports_failed(self):
        result, mock_export = self._run(
            parse_side_effect=[[], []],
            generate_side_effect=[],
            validate_side_effect=[],
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(mock_export.call_count, 0)


class _NoopRegistry:
    def save(self):
        pass


if __name__ == "__main__":
    unittest.main()
