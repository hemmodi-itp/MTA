import csv
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.catalog import catalog_manager
from tools.catalog.catalog_manager import (
    build_catalog_rows,
    stamp_execution_results,
    update_catalog,
    write_catalog_exports,
)


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _scenario(scenario_id, title, module_id="M01", objective="Do the thing"):
    return {
        "scenario_id": scenario_id,
        "title": title,
        "business_objective": objective,
        "module_id": module_id,
        "module_name": "Login",
    }


def _spec(spec_id, file, last_result=None, last_run=None, generation_mode=None):
    return {
        "spec_id": spec_id,
        "file": file,
        "last_result": last_result,
        "last_run": last_run,
        "generation_mode": generation_mode,
    }


class BuildCatalogRowsTests(unittest.TestCase):
    def setUp(self):
        self.project_dir = tempfile.mkdtemp()
        self.scenarios_path = os.path.join(self.project_dir, "test_comprehension", "business_scenarios.json")
        self.suite_path = os.path.join(self.project_dir, "test_creation", "test_suite.json")
        self.scripts_dir = os.path.join(self.project_dir, "test_creation", "test_scripts")

    def _touch_spec_file(self, relative_path):
        full = os.path.join(self.scripts_dir, relative_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write("// spec")

    def test_no_test_yet_when_scenario_has_no_spec_entry(self):
        _write_json(self.scenarios_path, {"scenarios": [_scenario("BS-001", "Login")]})

        rows = build_catalog_rows(self.project_dir)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "no_test_yet")
        self.assertEqual(rows[0]["spec_file"], "")

    def test_generated_when_spec_entry_and_file_both_exist(self):
        _write_json(self.scenarios_path, {"scenarios": [_scenario("BS-001", "Login")]})
        _write_json(self.suite_path, {"specs": [_spec("BS-001", "test_BS-001.spec.ts", last_result="passing")]})
        self._touch_spec_file("test_BS-001.spec.ts")

        rows = build_catalog_rows(self.project_dir)

        self.assertEqual(rows[0]["status"], "generated")
        self.assertEqual(rows[0]["last_result"], "passing")

    def test_missing_file_when_spec_entry_exists_but_file_deleted(self):
        _write_json(self.scenarios_path, {"scenarios": [_scenario("BS-001", "Login")]})
        _write_json(self.suite_path, {"specs": [_spec("BS-001", "test_BS-001.spec.ts")]})
        # deliberately do NOT create the file on disk

        rows = build_catalog_rows(self.project_dir)

        self.assertEqual(rows[0]["status"], "missing_file")

    def test_resilient_when_test_suite_json_does_not_exist(self):
        _write_json(self.scenarios_path, {"scenarios": [_scenario("BS-001", "Login")]})
        # no test_creation/test_suite.json written at all

        rows = build_catalog_rows(self.project_dir)

        self.assertEqual(rows[0]["status"], "no_test_yet")

    def test_description_is_truncated(self):
        long_objective = "x" * 200
        _write_json(self.scenarios_path, {"scenarios": [_scenario("BS-001", "Login", objective=long_objective)]})

        rows = build_catalog_rows(self.project_dir)

        self.assertLessEqual(len(rows[0]["description"]), 121)

    def test_generation_mode_is_surfaced_from_suite_entry(self):
        _write_json(self.scenarios_path, {"scenarios": [_scenario("BS-001", "Login")]})
        _write_json(self.suite_path, {"specs": [
            _spec("BS-001", "test_BS-001.spec.ts", generation_mode="action_library"),
        ]})
        self._touch_spec_file("test_BS-001.spec.ts")

        rows = build_catalog_rows(self.project_dir)

        self.assertEqual(rows[0]["generation_mode"], "action_library")

    def test_generation_mode_is_empty_string_when_absent(self):
        _write_json(self.scenarios_path, {"scenarios": [_scenario("BS-001", "Login")]})
        # no test_suite.json at all — "no_test_yet" status

        rows = build_catalog_rows(self.project_dir)

        self.assertEqual(rows[0]["generation_mode"], "")

    def test_rows_sorted_by_scenario_id(self):
        _write_json(self.scenarios_path, {"scenarios": [
            _scenario("BS-002", "Second"),
            _scenario("BS-001", "First"),
        ]})

        rows = build_catalog_rows(self.project_dir)

        self.assertEqual([r["scenario_id"] for r in rows], ["BS-001", "BS-002"])


class WriteCatalogExportsTests(unittest.TestCase):
    def setUp(self):
        self.project_dir = tempfile.mkdtemp()

    def test_csv_has_header_and_one_row_per_scenario(self):
        rows = [
            {"scenario_id": "BS-001", "module_id": "M01", "module_name": "Login",
             "title": "Login", "description": "desc", "status": "generated",
             "last_result": "passing", "spec_file": "f.spec.ts", "last_run": "2026-07-08"},
        ]
        paths = write_catalog_exports(self.project_dir, rows)

        with open(paths["csv"], encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 1)
        self.assertEqual(reader[0]["scenario_id"], "BS-001")

    def test_markdown_renders_a_table(self):
        rows = [
            {"scenario_id": "BS-001", "module_id": "M01", "module_name": "Login",
             "title": "Login", "description": "desc", "status": "generated",
             "last_result": "passing", "spec_file": "f.spec.ts", "last_run": "2026-07-08"},
        ]
        paths = write_catalog_exports(self.project_dir, rows)

        with open(paths["markdown"], encoding="utf-8") as f:
            content = f.read()
        self.assertIn("| scenario_id |", content)
        self.assertIn("BS-001", content)

    def test_second_call_overwrites_same_fixed_path_not_a_new_file(self):
        rows_v1 = [{"scenario_id": "BS-001", "module_id": "M01", "module_name": "Login",
                    "title": "Login", "description": "d", "status": "no_test_yet",
                    "last_result": "", "spec_file": "", "last_run": ""}]
        rows_v2 = rows_v1 + [{"scenario_id": "BS-002", "module_id": "M01", "module_name": "Login",
                              "title": "Logout", "description": "d", "status": "no_test_yet",
                              "last_result": "", "spec_file": "", "last_run": ""}]

        paths_v1 = write_catalog_exports(self.project_dir, rows_v1)
        paths_v2 = write_catalog_exports(self.project_dir, rows_v2)

        self.assertEqual(paths_v1["csv"], paths_v2["csv"])
        self.assertEqual(paths_v1["markdown"], paths_v2["markdown"])

        with open(paths_v2["csv"], encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 2)

        out_dir = os.path.join(self.project_dir, "test_creation")
        csv_files = [f for f in os.listdir(out_dir) if f.endswith(".csv")]
        self.assertEqual(csv_files, ["test_catalog.csv"])


class StampExecutionResultsTests(unittest.TestCase):
    def setUp(self):
        self.project_dir = tempfile.mkdtemp()
        self.suite_path = os.path.join(self.project_dir, "test_creation", "test_suite.json")

    def test_stamps_last_result_and_last_run_onto_matching_spec(self):
        _write_json(self.suite_path, {"specs": [_spec("M03_BS_006", "M03/test_M03_BS_006.spec.ts")]})

        updated = stamp_execution_results(self.project_dir, [
            {"business_scenario_id": "M03_BS_006", "status": "success"},
        ])

        self.assertEqual(updated, 1)
        with open(self.suite_path, encoding="utf-8") as f:
            suite = json.load(f)
        spec = suite["specs"][0]
        self.assertEqual(spec["last_result"], "passed")
        self.assertIsNotNone(spec["last_run"])

    def test_failed_status_is_preserved_not_normalized_to_passed(self):
        _write_json(self.suite_path, {"specs": [_spec("BS-001", "test_BS-001.spec.ts")]})

        stamp_execution_results(self.project_dir, [
            {"business_scenario_id": "BS-001", "status": "failed"},
        ])

        with open(self.suite_path, encoding="utf-8") as f:
            suite = json.load(f)
        self.assertEqual(suite["specs"][0]["last_result"], "failed")

    def test_falls_back_to_test_case_id_when_business_scenario_id_absent(self):
        _write_json(self.suite_path, {"specs": [_spec("BS-001", "test_BS-001.spec.ts")]})

        updated = stamp_execution_results(self.project_dir, [
            {"test_case_id": "BS-001", "status": "success"},
        ])

        self.assertEqual(updated, 1)

    def test_unmatched_result_is_skipped_not_an_error(self):
        _write_json(self.suite_path, {"specs": [_spec("BS-001", "test_BS-001.spec.ts")]})

        updated = stamp_execution_results(self.project_dir, [
            {"business_scenario_id": "BS-999", "status": "success"},
        ])

        self.assertEqual(updated, 0)

    def test_no_specs_at_all_returns_zero_without_writing(self):
        # no test_suite.json written
        updated = stamp_execution_results(self.project_dir, [
            {"business_scenario_id": "BS-001", "status": "success"},
        ])

        self.assertEqual(updated, 0)
        self.assertFalse(os.path.exists(self.suite_path))


class UpdateCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp_base = tempfile.mkdtemp()
        self._orig_base = catalog_manager._ASSETS_BASE
        catalog_manager._ASSETS_BASE = self.tmp_base

    def tearDown(self):
        catalog_manager._ASSETS_BASE = self._orig_base

    def test_update_catalog_writes_into_safe_named_project_dir(self):
        project_dir = os.path.join(self.tmp_base, "My_Project")
        _write_json(
            os.path.join(project_dir, "test_comprehension", "business_scenarios.json"),
            {"scenarios": [_scenario("BS-001", "Login")]},
        )

        result = update_catalog("My Project")

        self.assertEqual(result["rows"], 1)
        self.assertTrue(os.path.exists(result["csv"]))
        self.assertTrue(os.path.exists(result["markdown"]))


if __name__ == "__main__":
    unittest.main()
