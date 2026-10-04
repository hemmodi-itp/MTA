"""
Unit tests for agents/common/fallback_core.py

Focus: fallback_semantic_map — especially the mix of string steps (from the
synthetic BRD path) vs. dict steps (from the LLM comprehension path).
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.common.fallback_core import fallback_generate_script, fallback_semantic_map


_ELEMENT_USERNAME = {
    "locator_id": "LOC-0001",
    "tag": "input",
    "display_text": "",
    "playwright_locators": {
        "get_by_placeholder": {"placeholder": "Username"},
    },
    "technical_locators": {"css": "#user-name"},
    "recommended_locator": {"type": "id", "value": {"id": "user-name"}},
}

_ELEMENT_PASSWORD = {
    "locator_id": "LOC-0002",
    "tag": "input",
    "display_text": "",
    "playwright_locators": {
        "get_by_placeholder": {"placeholder": "Password"},
    },
    "technical_locators": {"css": "#password"},
    "recommended_locator": {"type": "id", "value": {"id": "password"}},
}

_ELEMENT_BUTTON = {
    "locator_id": "LOC-0003",
    "tag": "button",
    "display_text": "Login",
    "playwright_locators": {
        "get_by_role": {"role": "button", "name": "Login"},
    },
    "technical_locators": {"css": "#login-button"},
    "recommended_locator": {"type": "css", "value": {"css": "#login-button"}},
}

_ELEMENTS = [_ELEMENT_USERNAME, _ELEMENT_PASSWORD, _ELEMENT_BUTTON]


class TestFallbackSemanticMapStringSteps(unittest.TestCase):
    """Steps are plain strings — the synthetic BRD path that was crashing."""

    def _run(self, steps):
        scenarios = [
            {
                "scenario_id": "SC-001",
                "title": "Login flow",
                "steps": steps,
            }
        ]
        return fallback_semantic_map(scenarios, _ELEMENTS)

    def test_string_steps_do_not_raise(self):
        result = self._run([
            "Enter username in the input field",
            "Enter password in the input field",
            "Click the login button",
        ])
        self.assertIn("SC-001", result)

    def test_string_steps_return_correct_structure(self):
        result = self._run(["Enter username in the input field"])
        sc = result["SC-001"]
        self.assertEqual(sc["scenario_title"], "Login flow")
        self.assertIsInstance(sc["relevant_elements"], list)
        self.assertTrue(sc.get("fallback"))

    def test_string_steps_match_relevant_elements(self):
        result = self._run(["Enter username in the input field"])
        ids = [e["locator_id"] for e in result["SC-001"]["relevant_elements"]]
        # "username" token overlaps with LOC-0001 placeholder "Username"
        self.assertIn("LOC-0001", ids)

    def test_empty_string_steps_returns_empty_elements(self):
        result = self._run(["completely unrelated gibberish xyz123"])
        # No keyword overlap → no relevant elements, but scenario still present
        self.assertIn("SC-001", result)
        self.assertEqual(result["SC-001"]["relevant_elements"], [])

    def test_empty_steps_list(self):
        result = self._run([])
        self.assertIn("SC-001", result)
        self.assertEqual(result["SC-001"]["relevant_elements"], [])


class TestFallbackSemanticMapDictSteps(unittest.TestCase):
    """Steps are dicts — the LLM comprehension path."""

    def test_dict_steps_do_not_raise(self):
        scenarios = [
            {
                "scenario_id": "SC-002",
                "title": "Login",
                "steps": [
                    {"description": "Enter username", "action": "type"},
                    {"description": "Enter password", "action": "type"},
                ],
            }
        ]
        result = fallback_semantic_map(scenarios, _ELEMENTS)
        self.assertIn("SC-002", result)

    def test_dict_steps_match_elements(self):
        scenarios = [
            {
                "scenario_id": "SC-002",
                "title": "Login",
                # "input" token matches element tag "input"
                "steps": [{"description": "Type into the input field", "action": "type"}],
            }
        ]
        result = fallback_semantic_map(scenarios, _ELEMENTS)
        ids = [e["locator_id"] for e in result["SC-002"]["relevant_elements"]]
        self.assertIn("LOC-0001", ids)


class TestFallbackSemanticMapMixedSteps(unittest.TestCase):
    """Steps list mixes strings and dicts — defensive handling."""

    def test_mixed_steps_do_not_raise(self):
        scenarios = [
            {
                "scenario_id": "SC-003",
                "title": "Mixed",
                "steps": [
                    "Enter username",
                    {"description": "Click login button", "action": "click"},
                ],
            }
        ]
        result = fallback_semantic_map(scenarios, _ELEMENTS)
        self.assertIn("SC-003", result)


class TestFallbackSemanticMapNoElements(unittest.TestCase):
    """Empty element list always returns an empty relevant_elements per scenario."""

    def test_no_elements_returns_empty_relevant(self):
        scenarios = [{"scenario_id": "SC-004", "title": "T", "steps": ["click button"]}]
        result = fallback_semantic_map(scenarios, [])
        self.assertEqual(result["SC-004"]["relevant_elements"], [])


class TestFallbackSemanticMapPlaywrightExpr(unittest.TestCase):
    """Returned playwright_expr strings are well-formed."""

    def test_get_by_placeholder_expr(self):
        scenarios = [
            {"scenario_id": "SC-005", "title": "T", "steps": ["Enter username in the input"]}
        ]
        result = fallback_semantic_map(scenarios, [_ELEMENT_USERNAME])
        exprs = [e["playwright_expr"] for e in result["SC-005"]["relevant_elements"]]
        self.assertTrue(any("getByPlaceholder" in ex for ex in exprs))

    def test_get_by_role_expr(self):
        scenarios = [
            {"scenario_id": "SC-006", "title": "T", "steps": ["Click the login button"]}
        ]
        result = fallback_semantic_map(scenarios, [_ELEMENT_BUTTON])
        exprs = [e["playwright_expr"] for e in result["SC-006"]["relevant_elements"]]
        self.assertTrue(any("getByRole" in ex for ex in exprs))


class TestFallbackGenerateScript(unittest.TestCase):
    """fallback_generate_script must handle BusinessScenario.steps, which is
    List[str] in the live schema — the same string-vs-dict split already
    guarded for fallback_semantic_map above, but previously missing here."""

    def test_string_steps_do_not_raise(self):
        scenario = {
            "scenario_id": "M03_BS_010",
            "title": "View project status",
            "steps": ["Navigate to dashboard", "Click on project card"],
        }
        content = fallback_generate_script(scenario, [], {}, base_url="http://x")
        self.assertIn("M03_BS_010", content)
        self.assertIn("step 01", content)
        self.assertIn("Navigate to dashboard", content)

    def test_dict_steps_still_work(self):
        scenario = {
            "scenario_id": "BS-001",
            "title": "Login",
            "steps": [{"description": "Enter username", "action": "type"}],
        }
        content = fallback_generate_script(scenario, [], {}, base_url="http://x")
        self.assertIn("Enter username", content)

    def test_empty_steps_do_not_raise(self):
        scenario = {"scenario_id": "BS-002", "title": "No steps", "steps": []}
        content = fallback_generate_script(scenario, [], {}, base_url="http://x")
        self.assertIn("BS-002", content)

    def test_output_is_syntactically_plausible_playwright(self):
        scenario = {"scenario_id": "BS-003", "title": "T", "steps": ["do a thing"]}
        content = fallback_generate_script(scenario, [], {}, base_url="http://x")
        self.assertIn("import { test, expect }", content)
        self.assertIn("test.describe", content)


if __name__ == "__main__":
    unittest.main()
