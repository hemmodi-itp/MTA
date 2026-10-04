import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import (
    _scenario_element_map_coverage_warning,
    _test_data_drift_warning,
)


class TestDataDriftWarningTests(unittest.TestCase):
    """The concrete AWS_Test bug: test_data.json kept its old SC-001-style
    scenario ids after business_scenarios.json moved to M01_BS_001-style
    ids, so every _load_test_data_map lookup silently missed."""

    def test_warns_when_no_scenario_ids_overlap_at_all(self):
        scenarios = [{"scenario_id": "M01_BS_001"}, {"scenario_id": "M01_BS_002"}]
        test_data_map = {"SC-001": {}, "SC-002": {}}
        msg = _test_data_drift_warning(scenarios, test_data_map)
        self.assertIsNotNone(msg)
        self.assertIn("stale", msg)

    def test_no_warning_when_at_least_one_id_overlaps(self):
        scenarios = [{"scenario_id": "M01_BS_001"}, {"scenario_id": "M01_BS_002"}]
        test_data_map = {"M01_BS_001": {}, "SC-002": {}}
        self.assertIsNone(_test_data_drift_warning(scenarios, test_data_map))

    def test_no_warning_when_test_data_map_is_empty(self):
        self.assertIsNone(_test_data_drift_warning([{"scenario_id": "M01_BS_001"}], {}))

    def test_no_warning_when_no_scenarios(self):
        self.assertIsNone(_test_data_drift_warning([], {"SC-001": {}}))


class ScenarioElementMapCoverageWarningTests(unittest.TestCase):
    """The concrete geminiTest bug: business_scenarios.json grew from 3 to
    17 scenarios (14 new, real ones) but scenario_element_map.json was
    never regenerated — semantic_map simply wasn't rerun — so 14/17
    scenarios get zero relevant_elements and ScriptGenerationAgent renders
    them as near-empty specs (often just navigate() alone) with no signal
    why."""

    def test_warns_when_some_current_scenarios_have_no_map_entry(self):
        scenarios = [
            {"scenario_id": "SC-001"}, {"scenario_id": "M01_BS_001"}, {"scenario_id": "M01_BS_002"},
        ]
        scenario_map = {"SC-001": {"relevant_elements": []}}
        msg = _scenario_element_map_coverage_warning(scenarios, scenario_map)
        self.assertIsNotNone(msg)
        self.assertIn("2/3", msg)
        self.assertIn("M01_BS_001", msg)
        self.assertIn("M01_BS_002", msg)

    def test_no_warning_when_every_current_scenario_has_an_entry(self):
        scenarios = [{"scenario_id": "M01_BS_001"}, {"scenario_id": "M01_BS_002"}]
        scenario_map = {
            "M01_BS_001": {"relevant_elements": []},  # legitimately thin, not stale — has an entry
            "M01_BS_002": {"relevant_elements": [{"locator_id": "LOC-0001"}]},
        }
        self.assertIsNone(_scenario_element_map_coverage_warning(scenarios, scenario_map))

    def test_no_warning_when_scenario_map_is_entirely_empty(self):
        # Nothing has ever mapped anything yet (or a BRD-only project) —
        # a distinct, already-documented situation, not this staleness bug.
        self.assertIsNone(
            _scenario_element_map_coverage_warning([{"scenario_id": "M01_BS_001"}], {})
        )

    def test_no_warning_when_no_scenarios(self):
        self.assertIsNone(_scenario_element_map_coverage_warning([], {"SC-001": {}}))

    def test_truncates_sample_list_at_five_missing_ids(self):
        scenarios = [{"scenario_id": f"M01_BS_{i:03d}"} for i in range(10)]
        msg = _scenario_element_map_coverage_warning(scenarios, {})
        # scenario_map entirely empty -> None per the rule above; force a
        # partial-coverage case instead to exercise the truncation path.
        scenario_map = {"M01_BS_000": {"relevant_elements": []}}
        msg = _scenario_element_map_coverage_warning(scenarios, scenario_map)
        self.assertIsNotNone(msg)
        self.assertIn("9/10", msg)
        self.assertIn("...", msg)


if __name__ == "__main__":
    unittest.main()
