import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.state.review_queue import (
    flag_for_human_review,
    flag_missing_capability,
    record_locator_drift,
)


class FlagForHumanReviewTests(unittest.TestCase):
    def test_appends_entry_with_python_fallback_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag_for_human_review("proj", "script_generation", {"scenario_id": "BS-001"}, RuntimeError("boom"), output_dir=tmp)
            with open(os.path.join(tmp, "human_review_queue.json"), encoding="utf-8") as f:
                queue = json.load(f)
            self.assertEqual(len(queue), 1)
            self.assertEqual(queue[0]["kind"], "python_fallback")
            self.assertEqual(queue[0]["scenario_id"], "BS-001")


class FlagMissingCapabilityTests(unittest.TestCase):
    def test_writes_entry_when_gaps_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag_missing_capability("proj", "BS-001", ["swipeGesture"], [], output_dir=tmp)
            with open(os.path.join(tmp, "human_review_queue.json"), encoding="utf-8") as f:
                queue = json.load(f)
            self.assertEqual(len(queue), 1)
            self.assertEqual(queue[0]["kind"], "missing_capability")
            self.assertEqual(queue[0]["missing_actions"], ["swipeGesture"])

    def test_no_op_when_both_lists_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag_missing_capability("proj", "BS-001", [], [], output_dir=tmp)
            self.assertFalse(os.path.exists(os.path.join(tmp, "human_review_queue.json")))


class RecordLocatorDriftTests(unittest.TestCase):
    def test_writes_entry_with_added_updated_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_locator_drift(
                "proj", "M01", added=["a"], updated=["b"], possibly_removed=["c"], output_dir=tmp,
            )
            with open(os.path.join(tmp, "human_review_queue.json"), encoding="utf-8") as f:
                queue = json.load(f)
            self.assertEqual(queue[0]["kind"], "dom_drift")
            self.assertEqual(queue[0]["added"], ["a"])
            self.assertEqual(queue[0]["updated"], ["b"])
            self.assertEqual(queue[0]["possibly_removed"], ["c"])

    def test_kind_and_source_are_distinguishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_locator_drift(
                "proj", "_project", added=[], updated=["x"], possibly_removed=[],
                output_dir=tmp, kind="locator_map_drift", source="build_named_locator_map",
            )
            with open(os.path.join(tmp, "human_review_queue.json"), encoding="utf-8") as f:
                queue = json.load(f)
            self.assertEqual(queue[0]["kind"], "locator_map_drift")
            self.assertEqual(queue[0]["source"], "build_named_locator_map")

    def test_no_op_when_all_three_lists_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_locator_drift("proj", "M01", added=[], updated=[], possibly_removed=[], output_dir=tmp)
            self.assertFalse(os.path.exists(os.path.join(tmp, "human_review_queue.json")))

    def test_entries_from_different_calls_append_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_locator_drift("proj", "M01", added=["a"], updated=[], possibly_removed=[], output_dir=tmp)
            record_locator_drift("proj", "M02", added=["b"], updated=[], possibly_removed=[], output_dir=tmp)
            with open(os.path.join(tmp, "human_review_queue.json"), encoding="utf-8") as f:
                queue = json.load(f)
            self.assertEqual(len(queue), 2)


if __name__ == "__main__":
    unittest.main()
