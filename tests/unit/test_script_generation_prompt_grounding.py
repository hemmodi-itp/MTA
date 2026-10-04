import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import ScriptGenerationAgent

_VALID_PLAN = json.dumps({
    "tests": [{"name": "positive — x", "type": "positive", "steps": [{"action": "navigate"}]}],
    "missing_actions": [],
    "missing_locators": [],
})


class _CapturingLLM:
    def __init__(self, response=_VALID_PLAN):
        self.last_prompt = None
        self._response = response

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self._response


class PromptGroundingInstructionsTests(unittest.TestCase):
    """Guards against the action-library prompt regressing to allow
    hallucinated actions/locators/flows — the core mechanism is 'report
    missing_actions/missing_locators instead of guessing', not a specific
    wording, but these strings anchor that the rule is still present."""

    def setUp(self):
        self.agent = ScriptGenerationAgent(settings={})
        self.llm = _CapturingLLM()

    def _render_prompt(self, allowed_locators=None, flows_meta=None):
        self.agent._plan_via_llm(
            scenario={"scenario_id": "BS-001", "title": "Sample scenario"},
            allowed_locators=allowed_locators or [{"key": "submit_button", "description": "Submit"}],
            test_data={},
            base_url="https://example.com",
            flows_meta=flows_meta or {},
            llm=self.llm,
        )
        self.assertIsNotNone(self.llm.last_prompt)
        return self.llm.last_prompt

    def test_prompt_forbids_inventing_actions_locators_or_flows(self):
        prompt = self._render_prompt()
        self.assertIn("NEVER invent an action, locator_key, or flow name", prompt)

    def test_prompt_directs_gaps_to_missing_actions_and_missing_locators(self):
        prompt = self._render_prompt()
        self.assertIn("missing_actions", prompt)
        self.assertIn("missing_locators", prompt)

    def test_prompt_lists_only_this_scenarios_allowed_locator_keys(self):
        prompt = self._render_prompt(allowed_locators=[{"key": "search_box", "description": "Search"}])
        self.assertIn("search_box", prompt)

    def test_prompt_lists_allowed_flows(self):
        prompt = self._render_prompt(flows_meta={"login": ["username", "password"]})
        self.assertIn("login", prompt)

    def test_prompt_includes_both_few_shot_examples(self):
        prompt = self._render_prompt()
        self.assertIn("Example 1", prompt)
        self.assertIn("Example 2", prompt)
        self.assertIn("useFlow", prompt)

    def test_prompt_documents_soft_flag_and_page_error_action(self):
        prompt = self._render_prompt()
        self.assertIn('"soft": true', prompt)
        self.assertIn("verifyNoPageErrors", prompt)

    def test_prompt_forbids_markdown_fences(self):
        prompt = self._render_prompt()
        self.assertIn("No markdown fences", prompt)


if __name__ == "__main__":
    unittest.main()
