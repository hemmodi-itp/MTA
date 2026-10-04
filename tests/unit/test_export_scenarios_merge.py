import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.comprehension.export_scenarios import export_scenarios, load_existing_titles_by_module
from tools.comprehension.models import BusinessScenario


def _scenario(scenario_id, title, module_id):
    return BusinessScenario(
        scenario_id=scenario_id,
        title=title,
        business_objective=f"Verify {title}",
        actor="User",
        preconditions=[],
        steps=[f"Do {title}"],
        expected_result=f"{title} succeeds",
        module_id=module_id,
    )


class ExportScenariosMergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def _read_json(self):
        with open(os.path.join(self.tmp_dir, "business_scenarios.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_second_module_run_preserves_first_modules_scenarios(self):
        export_scenarios(
            [_scenario("M01_BS_001", "Login", "M01")],
            self.tmp_dir, "proj", module_ids=["M01"],
        )
        export_scenarios(
            [_scenario("M03_BS_001", "Dashboard loads widgets", "M03")],
            self.tmp_dir, "proj", module_ids=["M03"],
        )

        payload = self._read_json()
        ids = {s["scenario_id"] for s in payload["scenarios"]}
        self.assertEqual(ids, {"M01_BS_001", "M03_BS_001"})
        self.assertEqual(set(payload["modules"]), {"M01", "M03"})

    def test_rerunning_same_module_upserts_rather_than_duplicates(self):
        export_scenarios(
            [_scenario("M03_BS_001", "Dashboard loads widgets", "M03")],
            self.tmp_dir, "proj", module_ids=["M03"],
        )
        export_scenarios(
            [_scenario("M03_BS_001", "Dashboard loads widgets (updated)", "M03")],
            self.tmp_dir, "proj", module_ids=["M03"],
        )

        payload = self._read_json()
        self.assertEqual(payload["total_scenarios"], 1)
        self.assertEqual(payload["scenarios"][0]["title"], "Dashboard loads widgets (updated)")

    def test_merge_false_overwrites_like_legacy_behaviour(self):
        export_scenarios(
            [_scenario("M01_BS_001", "Login", "M01")],
            self.tmp_dir, "proj", module_ids=["M01"],
        )
        export_scenarios(
            [_scenario("M03_BS_001", "Dashboard loads widgets", "M03")],
            self.tmp_dir, "proj", module_ids=["M03"], merge=False,
        )

        payload = self._read_json()
        ids = {s["scenario_id"] for s in payload["scenarios"]}
        self.assertEqual(ids, {"M03_BS_001"})


class LoadExistingTitlesByModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_returns_empty_dict_when_no_file_yet(self):
        self.assertEqual(load_existing_titles_by_module(self.tmp_dir), {})

    def test_groups_titles_by_module_id(self):
        export_scenarios(
            [
                _scenario("M01_BS_001", "Login", "M01"),
                _scenario("M01_BS_002", "Logout", "M01"),
                _scenario("M03_BS_001", "Dashboard loads widgets", "M03"),
            ],
            self.tmp_dir, "proj", module_ids=["M01", "M03"],
        )

        by_module = load_existing_titles_by_module(self.tmp_dir)

        self.assertEqual(
            {e["scenario_id"] for e in by_module["M01"]},
            {"M01_BS_001", "M01_BS_002"},
        )
        self.assertEqual(
            {e["title"] for e in by_module["M01"]},
            {"Login", "Logout"},
        )
        self.assertEqual(
            by_module["M03"],
            [{"scenario_id": "M03_BS_001", "title": "Dashboard loads widgets"}],
        )

    def test_ignores_scenarios_with_no_module_id(self):
        export_scenarios(
            [_scenario("BS-001", "No module scenario", None)],
            self.tmp_dir, "proj",
        )
        self.assertEqual(load_existing_titles_by_module(self.tmp_dir), {})


if __name__ == "__main__":
    unittest.main()
