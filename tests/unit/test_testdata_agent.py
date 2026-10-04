import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.testdata.agent import TestDataAgent


def _scenario(scenario_id, module_id=None):
    return SimpleNamespace(scenario_id=scenario_id, module_id=module_id, title=scenario_id, steps=[])


def _dataset(positive_dataset=None, negative_variants=None):
    return SimpleNamespace(
        positive_dataset=positive_dataset if positive_dataset is not None else ["field"],
        negative_variants=negative_variants if negative_variants is not None else [],
    )


class _FakeContext:
    scenarios_with_test_data = set()
    format_guide_testdata = ""
    existing_test_data_raw = {}


class TestDataAgentBatchExceptionHandlingTests(unittest.TestCase):
    """Per-scenario exceptions used to be caught narrowly (ValueError only) —
    any other exception type propagated and discarded every other
    already-generated good result in the batch. Broadened to Exception."""

    def setUp(self):
        self.agent = TestDataAgent(settings={})
        self.agent._log = MagicMock()

    def _run_pipeline(self, scenarios, generate_side_effect):
        with patch("agents.test_creation.testdata.agent.load_scenarios", return_value=scenarios), \
             patch("agents.test_creation.testdata.agent.ProjectArtifactContext.load", return_value=_FakeContext()), \
             patch("agents.test_creation.testdata.agent.load_test_generation_config",
                   return_value={"max_negative_cases": 1, "max_boundary_cases": 1, "max_data_iterations": 3}), \
             patch("agents.test_creation.testdata.agent.generate_test_data", side_effect=generate_side_effect), \
             patch("agents.test_creation.testdata.agent.validate_test_data",
                   side_effect=lambda datasets: (datasets, [])), \
             patch("agents.test_creation.testdata.agent.export_test_data", return_value={}):
            llm = MagicMock()
            return self.agent._llm_pipeline({"project_name": "proj"}, {}, llm=llm)

    def test_non_value_error_on_one_scenario_does_not_discard_the_batch(self):
        scenarios = [_scenario("BS-001"), _scenario("BS-002"), _scenario("BS-003")]

        def _generate(**kwargs):
            scenario = kwargs["scenario"]
            if scenario.scenario_id == "BS-002":
                raise KeyError("field_name")
            return _dataset()

        result = self._run_pipeline(scenarios, _generate)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["datasets_generated"], 2)

    def test_value_error_still_drops_only_that_scenario(self):
        scenarios = [_scenario("BS-001"), _scenario("BS-002")]

        def _generate(**kwargs):
            scenario = kwargs["scenario"]
            if scenario.scenario_id == "BS-002":
                raise ValueError("bad response")
            return _dataset()

        result = self._run_pipeline(scenarios, _generate)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["datasets_generated"], 1)


class TestDataAgentCoverageSignalTests(unittest.TestCase):
    """coverage_pct/coverage_warning were dropped by the revamp — an
    operational signal for "the LLM under-delivered for most scenarios"
    silently disappeared. Restored, with a predicate that treats a
    legitimately-empty read-only dataset (no positive_dataset AND no
    negative_variants) as covered, not a gap."""

    def setUp(self):
        self.agent = TestDataAgent(settings={})
        self.agent._log = MagicMock()

    def _run_pipeline(self, scenarios, datasets_by_id):
        def _generate(**kwargs):
            return datasets_by_id[kwargs["scenario"].scenario_id]

        with patch("agents.test_creation.testdata.agent.load_scenarios", return_value=scenarios), \
             patch("agents.test_creation.testdata.agent.ProjectArtifactContext.load", return_value=_FakeContext()), \
             patch("agents.test_creation.testdata.agent.load_test_generation_config",
                   return_value={"max_negative_cases": 1, "max_boundary_cases": 1, "max_data_iterations": 3}), \
             patch("agents.test_creation.testdata.agent.generate_test_data", side_effect=_generate), \
             patch("agents.test_creation.testdata.agent.validate_test_data",
                   side_effect=lambda datasets: (datasets, [])), \
             patch("agents.test_creation.testdata.agent.export_test_data", return_value={}):
            llm = MagicMock()
            return self.agent._llm_pipeline({"project_name": "proj"}, {}, llm=llm)

    def test_full_coverage_when_all_scenarios_get_a_positive_dataset(self):
        scenarios = [_scenario("BS-001"), _scenario("BS-002")]
        datasets = {
            "BS-001": _dataset(positive_dataset=["field"]),
            "BS-002": _dataset(positive_dataset=["field"]),
        }
        result = self._run_pipeline(scenarios, datasets)
        self.assertEqual(result["coverage_pct"], 100)
        self.assertFalse(result["coverage_warning"])

    def test_read_only_legitimately_empty_dataset_counts_as_covered(self):
        scenarios = [_scenario("BS-001"), _scenario("BS-002")]
        datasets = {
            "BS-001": _dataset(positive_dataset=["field"]),
            "BS-002": _dataset(positive_dataset=[], negative_variants=[]),  # legit read-only pass-through
        }
        result = self._run_pipeline(scenarios, datasets)
        self.assertEqual(result["coverage_pct"], 100)
        self.assertFalse(result["coverage_warning"])

    def test_low_coverage_triggers_warning(self):
        scenarios = [_scenario("BS-001"), _scenario("BS-002"), _scenario("BS-003")]
        datasets = {
            "BS-001": _dataset(positive_dataset=[], negative_variants=["something"]),  # gap: has variants, no positive
            "BS-002": _dataset(positive_dataset=[], negative_variants=["something"]),
            "BS-003": _dataset(positive_dataset=["field"]),
        }
        result = self._run_pipeline(scenarios, datasets)
        self.assertEqual(result["coverage_pct"], 33)
        self.assertTrue(result["coverage_warning"])


if __name__ == "__main__":
    unittest.main()
