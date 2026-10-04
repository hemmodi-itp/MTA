import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.common.failure_classifier import LLMResponseValidationError
from agents.test_creation.script_generation.agent import ScriptGenerationAgent, _validate_plan, ALLOWED_ACTIONS

_ALLOWED_KEYS = {"search_box", "search_button", "results_list"}
_ALLOWED_FLOWS = {"login": ["username", "password"]}


def _plan(steps, extra=None):
    plan = {"tests": [{"name": "positive — x", "type": "positive", "steps": steps}]}
    plan.update(extra or {})
    return plan


class ValidatePlanTests(unittest.TestCase):
    """_validate_plan is the actual enforcement gate on top of the prompt's
    'never invent' instruction — every action/locator_key/flow name in a
    generated plan must be schema-validated against what was actually
    offered for this scenario."""

    def test_valid_plan_with_locator_and_flow_passes(self):
        plan = _plan([
            {"action": "useFlow", "flow": "login", "args": {"username": "u", "password": "p"}},
            {"action": "enterText", "locator_key": "search_box", "value": "x"},
            {"action": "verifyVisible", "locator_key": "results_list", "message": "shows results"},
        ])
        _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)  # no raise

    def test_missing_tests_list_rejected(self):
        with self.assertRaises(LLMResponseValidationError):
            _validate_plan({}, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)

    def test_disallowed_action_rejected(self):
        plan = _plan([{"action": "hackTheMainframe", "locator_key": "search_box"}])
        with self.assertRaises(LLMResponseValidationError) as ctx:
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)
        self.assertIn("disallowed action", str(ctx.exception))

    def test_disallowed_locator_key_rejected(self):
        plan = _plan([{"action": "click", "locator_key": "invented_button"}])
        with self.assertRaises(LLMResponseValidationError) as ctx:
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)
        self.assertIn("disallowed locator_key", str(ctx.exception))

    def test_unknown_flow_name_rejected(self):
        plan = _plan([{"action": "useFlow", "flow": "checkout", "args": {}}])
        with self.assertRaises(LLMResponseValidationError) as ctx:
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)
        self.assertIn("unknown flow", str(ctx.exception))

    def test_drag_and_drop_validates_both_locator_keys(self):
        plan = _plan([{"action": "dragAndDrop", "locator_key": "search_box", "target_locator_key": "ghost"}])
        with self.assertRaises(LLMResponseValidationError) as ctx:
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)
        self.assertIn("dragAndDrop", str(ctx.exception))

    def test_press_key_allows_null_locator(self):
        plan = _plan([{"action": "pressKey", "locator_key": None, "value": "Enter"}])
        _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)  # no raise

    def test_no_locator_action_needs_no_locator_key(self):
        plan = _plan([
            {"action": "navigate"},
            {"action": "verifyNoPageErrors", "message": "no JS errors"},
            {"action": "verifyUrl", "value": "/x", "message": "on x"},
        ])
        _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)  # no raise

    def test_empty_steps_list_rejected(self):
        plan = _plan([])
        with self.assertRaises(LLMResponseValidationError):
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)

    def test_missing_locators_field_must_be_a_list(self):
        plan = _plan([{"action": "navigate"}], extra={"missing_locators": "not a list"})
        with self.assertRaises(LLMResponseValidationError):
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)

    def test_verify_contains_text_missing_value_rejected(self):
        """Regression test: spec_renderer's ARG_BUILDERS does a hard step["value"]
        for verifyContainsText — before VALUE_REQUIRED_ACTIONS was enforced here,
        a plan like this passed _validate_plan and then crashed render_spec_from_plan
        with an unhandled KeyError, taking down the whole script_generation run."""
        plan = _plan([{"action": "verifyContainsText", "locator_key": "results_list", "message": "shows results"}])
        with self.assertRaises(LLMResponseValidationError) as ctx:
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)
        self.assertIn("missing required 'value'", str(ctx.exception))

    def test_verify_count_missing_value_rejected(self):
        plan = _plan([{"action": "verifyCount", "locator_key": "results_list"}])
        with self.assertRaises(LLMResponseValidationError) as ctx:
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)
        self.assertIn("missing required 'value'", str(ctx.exception))

    def test_verify_count_zero_value_is_not_treated_as_missing(self):
        plan = _plan([{"action": "verifyCount", "locator_key": "results_list", "value": 0}])
        _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)  # no raise

    def test_enter_text_missing_value_rejected(self):
        plan = _plan([{"action": "enterText", "locator_key": "search_box"}])
        with self.assertRaises(LLMResponseValidationError) as ctx:
            _validate_plan(plan, "BS-001", ALLOWED_ACTIONS, _ALLOWED_KEYS, _ALLOWED_FLOWS)
        self.assertIn("missing required 'value'", str(ctx.exception))


class LocatorEntryResolvesTests(unittest.TestCase):
    """The live dry-run check ScriptGenerationAgent runs once per project per
    module (_validate_locator_map_live) resolves a locator_map.json entry the
    same way LocatorManager.ts does at test-run time."""

    def test_css_type_resolves_via_locator(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 1
        self.assertTrue(ScriptGenerationAgent._locator_entry_resolves(page, {"type": "css", "locator": "#id"}))
        page.locator.assert_called_once_with("#id")

    def test_role_type_with_name_resolves_via_get_by_role(self):
        page = MagicMock()
        page.get_by_role.return_value.count.return_value = 1
        entry = {"type": "role", "locator": "button", "name": "Submit"}
        self.assertTrue(ScriptGenerationAgent._locator_entry_resolves(page, entry))
        page.get_by_role.assert_called_once_with("button", name="Submit")

    def test_zero_count_is_unresolved(self):
        page = MagicMock()
        page.get_by_placeholder.return_value.count.return_value = 0
        entry = {"type": "placeholder", "locator": "Ghost"}
        self.assertFalse(ScriptGenerationAgent._locator_entry_resolves(page, entry))

    def test_ambiguous_multi_match_is_unresolved(self):
        # The real SC-001/SC-003 bug: a role="button" name="Sign in" locator
        # matched 2 elements (a text button + an icon button shown
        # responsively) — a Playwright strict-mode violation at runtime that
        # the old "count() > 0" check missed entirely, reporting it as fine.
        page = MagicMock()
        page.get_by_role.return_value.count.return_value = 2
        entry = {"type": "role", "locator": "button", "name": "Sign in"}
        self.assertFalse(ScriptGenerationAgent._locator_entry_resolves(page, entry))

    def test_label_and_testid_types_resolve(self):
        page = MagicMock()
        page.get_by_label.return_value.count.return_value = 1
        page.get_by_test_id.return_value.count.return_value = 1
        self.assertTrue(ScriptGenerationAgent._locator_entry_resolves(page, {"type": "label", "locator": "Email"}))
        self.assertTrue(ScriptGenerationAgent._locator_entry_resolves(page, {"type": "testid", "locator": "submit-btn"}))

    def test_resolution_error_is_permissive_not_a_rejection(self):
        page = MagicMock()
        page.locator.side_effect = RuntimeError("boom")
        self.assertTrue(ScriptGenerationAgent._locator_entry_resolves(page, {"type": "css", "locator": "#x"}))

    def test_unknown_type_is_permissive(self):
        page = MagicMock()
        self.assertTrue(ScriptGenerationAgent._locator_entry_resolves(page, {"type": "carrier-pigeon", "locator": "x"}))


if __name__ == "__main__":
    unittest.main()
