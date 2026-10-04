import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.state.project_state_manager import graduate_additions


class GraduateAdditionsTests(unittest.TestCase):
    def test_passed_test_case_leaves_new_additions(self):
        state = {"new_additions": ["BS-001", "BS-002"]}

        state = graduate_additions(state, {"results": [
            {"test_case_id": "BS-001", "status": "success"},
        ]})

        self.assertEqual(state["new_additions"], ["BS-002"])

    def test_failed_test_case_stays_in_new_additions(self):
        state = {"new_additions": ["BS-001"]}

        state = graduate_additions(state, {"results": [
            {"test_case_id": "BS-001", "status": "failed"},
        ]})

        self.assertEqual(state["new_additions"], ["BS-001"])

    def test_empty_run_results_leaves_new_additions_unchanged(self):
        state = {"new_additions": ["BS-001", "BS-002"]}

        state = graduate_additions(state, {})

        self.assertEqual(state["new_additions"], ["BS-001", "BS-002"])

    def test_accepts_id_key_as_well_as_test_case_id(self):
        state = {"new_additions": ["BS-001"]}

        state = graduate_additions(state, {"results": [{"id": "BS-001", "status": "passed"}]})

        self.assertEqual(state["new_additions"], [])


if __name__ == "__main__":
    unittest.main()
