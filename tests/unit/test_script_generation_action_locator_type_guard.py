import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import _flag_action_locator_type_mismatches


def _plan(steps):
    return {"tests": [{"name": "positive — x", "type": "positive", "steps": steps}]}


class FlagActionLocatorTypeMismatchesTests(unittest.TestCase):
    """The real geminiTest bug: the prompt textarea was never discovered as
    its own locator, so every enterText step got pointed at the page's
    microphone button instead (role="button") — filling nothing, since a
    button isn't fillable. This guard catches that class before render."""

    def test_enter_text_on_a_button_role_locator_is_dropped(self):
        locator_map = {"mic_button": {"type": "role", "locator": "button", "name": "Microphone"}}
        plan = _plan([
            {"action": "navigate"},
            {"action": "enterText", "locator_key": "mic_button", "value": "hello"},
        ])
        new_plan, dropped = _flag_action_locator_type_mismatches(plan, locator_map)

        self.assertEqual(len(dropped), 1)
        self.assertIn("mic_button", dropped[0])
        steps = new_plan["tests"][0]["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["action"], "navigate")

    def test_enter_text_on_a_link_role_locator_is_dropped(self):
        locator_map = {"nav_link": {"type": "role", "locator": "link", "name": "About"}}
        plan = _plan([{"action": "clearAndEnterText", "locator_key": "nav_link", "value": "x"}])
        new_plan, dropped = _flag_action_locator_type_mismatches(plan, locator_map)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(new_plan["tests"], [])  # its only step was dropped -> test excluded

    def test_enter_text_on_a_real_textbox_is_kept(self):
        locator_map = {"prompt_input": {"type": "role", "locator": "textbox", "name": "Enter a prompt"}}
        plan = _plan([{"action": "enterText", "locator_key": "prompt_input", "value": "hi"}])
        new_plan, dropped = _flag_action_locator_type_mismatches(plan, locator_map)
        self.assertEqual(dropped, [])
        self.assertEqual(new_plan, plan)

    def test_css_typed_locator_is_never_second_guessed(self):
        # A css-typed entry's real element kind isn't knowable without a live
        # DOM query — this guard only judges role-typed entries, staying a
        # targeted, high-confidence check rather than a guess.
        locator_map = {"some_field": {"type": "css", "locator": "div > input"}}
        plan = _plan([{"action": "enterText", "locator_key": "some_field", "value": "x"}])
        new_plan, dropped = _flag_action_locator_type_mismatches(plan, locator_map)
        self.assertEqual(dropped, [])
        self.assertEqual(new_plan, plan)

    def test_unknown_locator_key_is_left_alone(self):
        plan = _plan([{"action": "enterText", "locator_key": "not_in_map", "value": "x"}])
        new_plan, dropped = _flag_action_locator_type_mismatches(plan, {})
        self.assertEqual(dropped, [])

    def test_click_on_a_button_role_locator_is_never_flagged(self):
        # click is the correct action for a button — only enterText/
        # clearAndEnterText are ever mismatched against non-fillable roles.
        locator_map = {"submit_button": {"type": "role", "locator": "button", "name": "Submit"}}
        plan = _plan([{"action": "click", "locator_key": "submit_button"}])
        new_plan, dropped = _flag_action_locator_type_mismatches(plan, locator_map)
        self.assertEqual(dropped, [])

    def test_a_test_with_only_a_mismatched_step_is_dropped_entirely(self):
        locator_map = {"mic_button": {"type": "role", "locator": "button", "name": "Microphone"}}
        plan = _plan([{"action": "enterText", "locator_key": "mic_button", "value": "hi"}])
        new_plan, dropped = _flag_action_locator_type_mismatches(plan, locator_map)
        self.assertEqual(len(dropped), 1)
        self.assertIn("mic_button", dropped[0])
        self.assertEqual(new_plan["tests"], [])


if __name__ == "__main__":
    unittest.main()
