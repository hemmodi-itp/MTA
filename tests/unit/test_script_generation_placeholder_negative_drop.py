import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import (
    _allowed_locator_entries_for_scenario,
    _drop_placeholder_negative_tests,
)


class DropPlaceholderNegativeTestsTests(unittest.TestCase):
    """The concrete bug: a nav-menu click intent (no real invalid-input
    pathway) got a fabricated "negative" test asserting a heading equals ""
    with no basis in test_data — a trivially-passing, meaningless assertion.
    This guard drops exactly that pattern while leaving genuine negative
    tests (backed by a real expected_error) untouched."""

    def test_drops_negative_test_with_only_empty_string_assertions_and_no_test_data_basis(self):
        plan = {
            "tests": [
                {"name": "positive — nav works", "type": "positive", "steps": [
                    {"action": "click", "locator_key": "products_link"},
                ]},
                {"name": "negative — fabricated", "type": "negative", "steps": [
                    {"action": "verifyText", "locator_key": "heading", "value": "", "message": "should be empty"},
                ]},
            ]
        }
        new_plan, dropped = _drop_placeholder_negative_tests(plan, test_data={})
        self.assertEqual(dropped, ["negative — fabricated"])
        self.assertEqual(len(new_plan["tests"]), 1)
        self.assertEqual(new_plan["tests"][0]["type"], "positive")

    def test_keeps_negative_test_when_test_data_has_a_real_expected_error(self):
        plan = {
            "tests": [
                {"name": "negative — invalid email", "type": "negative", "steps": [
                    {"action": "verifyText", "locator_key": "heading", "value": "", "message": "should be empty"},
                ]},
            ]
        }
        test_data = {
            "negative_variants": [
                {"variant_id": "NEG-001", "iterations": [{"expected_error": "Invalid email format"}]},
            ]
        }
        new_plan, dropped = _drop_placeholder_negative_tests(plan, test_data)
        self.assertEqual(dropped, [])
        self.assertEqual(len(new_plan["tests"]), 1)

    def test_keeps_negative_test_with_a_non_empty_assertion(self):
        plan = {
            "tests": [
                {"name": "negative — error banner shown", "type": "negative", "steps": [
                    {"action": "verifyVisible", "locator_key": "error_banner", "message": "error should show"},
                ]},
            ]
        }
        new_plan, dropped = _drop_placeholder_negative_tests(plan, test_data={})
        self.assertEqual(dropped, [])
        self.assertEqual(len(new_plan["tests"]), 1)

    def test_positive_and_boundary_tests_are_never_dropped(self):
        plan = {
            "tests": [
                {"name": "boundary — max length", "type": "boundary", "steps": [
                    {"action": "verifyValue", "locator_key": "field", "value": "", "message": "x"},
                ]},
            ]
        }
        new_plan, dropped = _drop_placeholder_negative_tests(plan, test_data={})
        self.assertEqual(dropped, [])
        self.assertEqual(len(new_plan["tests"]), 1)

    def test_no_tests_key_is_a_noop(self):
        plan = {"missing_actions": [], "missing_locators": []}
        new_plan, dropped = _drop_placeholder_negative_tests(plan, test_data={})
        self.assertEqual(dropped, [])
        self.assertEqual(new_plan, plan)


class AllowedLocatorEntriesEnrichmentTests(unittest.TestCase):
    def test_passes_through_intent_fields_when_present(self):
        elements = [{
            "locator_id": "LOC-0001", "action": "fill", "expected_result": "username_entered",
            "cluster": "login", "confidence": 0.9,
        }]
        reverse_index = {"LOC-0001": "username_field"}
        locator_map = {"username_field": {"description": "username input"}}
        result = _allowed_locator_entries_for_scenario(elements, reverse_index, locator_map)
        self.assertEqual(result[0]["key"], "username_field")
        self.assertEqual(result[0]["action"], "fill")
        self.assertEqual(result[0]["expected_result"], "username_entered")
        self.assertEqual(result[0]["cluster"], "login")
        self.assertEqual(result[0]["confidence"], 0.9)

    def test_omits_intent_fields_when_absent(self):
        elements = [{"locator_id": "LOC-0001"}]
        reverse_index = {"LOC-0001": "username_field"}
        locator_map = {"username_field": {"description": "username input"}}
        result = _allowed_locator_entries_for_scenario(elements, reverse_index, locator_map)
        self.assertNotIn("cluster", result[0])
        self.assertNotIn("confidence", result[0])
        self.assertEqual(set(result[0].keys()), {"key", "description"})

    def test_unresolvable_keys_still_excluded(self):
        elements = [{"locator_id": "LOC-0001", "cluster": "login"}]
        reverse_index = {"LOC-0001": "username_field"}
        locator_map = {"username_field": {"description": "x"}}
        result = _allowed_locator_entries_for_scenario(
            elements, reverse_index, locator_map, unresolvable_keys={"username_field"},
        )
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
