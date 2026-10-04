import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.orchestrator.agent import (
    OrchestratorAgent,
    _extract_test_case_id,
    _resolve_execution_output,
    _with_test_case_ids,
)
from agents.registry_setup import build_default_registry


def _make_orchestrator():
    return OrchestratorAgent(
        settings={},
        agents_config={"agents": {}},
        registry=build_default_registry(),
        run_id="test-run-id",
    )


class ExtractTestCaseIdTests(unittest.TestCase):
    def test_extracts_spec_id_from_nested_path(self):
        self.assertEqual(
            _extract_test_case_id("M02/test_BS-007_search_for_products.spec.ts"),
            "BS-007",
        )

    def test_extracts_module_scoped_id_with_underscores(self):
        self.assertEqual(
            _extract_test_case_id("M03/test_M03_BS_006_verify_page_title.spec.ts"),
            "M03_BS_006",
        )

    def test_extracts_sc_prefixed_id(self):
        self.assertEqual(
            _extract_test_case_id("test_SC-001_use_appevolve.spec.ts"),
            "SC-001",
        )

    def test_returns_empty_string_when_no_match(self):
        self.assertEqual(_extract_test_case_id("M02/no_id_here.spec.ts"), "")

    def test_handles_empty_input(self):
        self.assertEqual(_extract_test_case_id(""), "")


class ResolveExecutionOutputTests(unittest.TestCase):
    def test_prefers_ui_execution_key(self):
        outputs = {"ui_execution": {"results": [{"status": "success"}]}, "execution": {"results": []}}
        self.assertEqual(_resolve_execution_output(outputs), {"results": [{"status": "success"}]})

    def test_falls_back_to_legacy_execution_key(self):
        outputs = {"execution": {"results": [{"status": "failed"}]}}
        self.assertEqual(_resolve_execution_output(outputs), {"results": [{"status": "failed"}]})

    def test_returns_empty_dict_when_neither_key_present(self):
        self.assertEqual(_resolve_execution_output({"discovery": {}}), {})


class WithTestCaseIdsTests(unittest.TestCase):
    def test_annotates_results_missing_test_case_id(self):
        result = {
            "status": "success",
            "results": [
                {"spec_file": "M01/test_BS-001_login.spec.ts", "status": "success"},
                {"spec_file": "M01/test_BS-002_logout.spec.ts", "status": "failed"},
            ],
        }

        annotated = _with_test_case_ids(result)

        self.assertEqual(annotated["results"][0]["test_case_id"], "BS-001")
        self.assertEqual(annotated["results"][1]["test_case_id"], "BS-002")
        # Original input must not be mutated.
        self.assertNotIn("test_case_id", result["results"][0])

    def test_does_not_override_existing_test_case_id(self):
        result = {"results": [{"spec_file": "M01/test_BS-001_login.spec.ts", "test_case_id": "custom-id"}]}

        annotated = _with_test_case_ids(result)

        self.assertEqual(annotated["results"][0]["test_case_id"], "custom-id")

    def test_passes_through_result_without_results_key(self):
        result = {"status": "skipped", "reason": "no_new_additions"}

        self.assertEqual(_with_test_case_ids(result), result)


class MergeStepIntoStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_name = "test_merge_project"
        self.project_dir = os.path.join(self.tmp_dir, self.project_name)
        os.makedirs(os.path.join(self.project_dir, "test_creation"), exist_ok=True)

        self.patcher = patch(
            "agents.orchestrator.agent._PROJECTS_DIR", self.tmp_dir
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_test_suite(self, specs):
        suite_path = os.path.join(self.project_dir, "test_creation", "test_suite.json")
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump({"specs": specs}, f)

    def test_script_generation_step_populates_test_cases(self):
        self._write_test_suite([
            {"spec_id": "BS-001", "module_id": "M01", "scenario_title": "Standard login"},
            {"spec_id": "BS-002", "module_id": "M01", "scenario_title": "Guest access"},
        ])

        orchestrator = _make_orchestrator()
        state = {"test_cases": {}, "business_scenarios": {}, "summary": {"total_test_cases": 0}}

        state = orchestrator._merge_step_into_state(
            "script_generation", {"status": "success"}, state, self.project_name, ""
        )

        self.assertEqual(state["summary"]["total_test_cases"], 2)
        self.assertIn("BS-001", state["test_cases"])
        self.assertIn("BS-001", state["new_additions"])

    def test_script_generation_step_is_noop_when_suite_missing(self):
        orchestrator = _make_orchestrator()
        state = {"test_cases": {}, "business_scenarios": {}, "summary": {"total_test_cases": 0}}

        state = orchestrator._merge_step_into_state(
            "script_generation", {"status": "success"}, state, self.project_name, ""
        )

        self.assertEqual(state["summary"]["total_test_cases"], 0)

    def test_ui_execution_step_merges_run_results_by_extracted_id(self):
        self._write_test_suite([{"spec_id": "BS-001", "module_id": "M01", "scenario_title": "Standard login"}])

        orchestrator = _make_orchestrator()
        state = {"test_cases": {}, "business_scenarios": {}, "summary": {"total_test_cases": 0}}
        state = orchestrator._merge_step_into_state(
            "script_generation", {"status": "success"}, state, self.project_name, ""
        )

        execution_result = {
            "status": "success",
            "results": [{"spec_file": "M01/test_BS-001_standard_login.spec.ts", "status": "success"}],
        }
        state = orchestrator._merge_step_into_state(
            "ui_execution", execution_result, state, self.project_name, ""
        )

        self.assertEqual(state["test_cases"]["BS-001"]["status"], "passing")
        self.assertEqual(state["summary"]["passing_tests"], 1)


if __name__ == "__main__":
    unittest.main()
