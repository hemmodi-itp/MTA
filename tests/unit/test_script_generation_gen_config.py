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


class PlanViaLlmGenConfigTests(unittest.TestCase):
    def setUp(self):
        self.agent = ScriptGenerationAgent(settings={})

    def test_default_gen_config_substituted_into_prompt(self):
        llm = _CapturingLLM()
        self.agent._plan_via_llm(
            scenario={"scenario_id": "M03_BS_001", "title": "Scenario"},
            allowed_locators=[], test_data={}, base_url="http://x", flows_meta={}, llm=llm,
        )
        self.assertIn("At most 1 negative test(s)", llm.last_prompt)
        self.assertIn("At most 1 boundary test(s)", llm.last_prompt)
        self.assertIn("up to 3", llm.last_prompt)
        self.assertIn("alternate value sets", llm.last_prompt)

    def test_custom_gen_config_substituted_into_prompt(self):
        llm = _CapturingLLM()
        self.agent._plan_via_llm(
            scenario={"scenario_id": "M03_BS_001", "title": "Scenario"},
            allowed_locators=[], test_data={}, base_url="http://x", flows_meta={}, llm=llm,
            gen_config={"max_negative_cases": 2, "max_boundary_cases": 3, "max_data_iterations": 5},
        )
        self.assertIn("At most 2 negative test(s)", llm.last_prompt)
        self.assertIn("At most 3 boundary test(s)", llm.last_prompt)
        self.assertIn("up to 5", llm.last_prompt)
        self.assertIn("alternate value sets", llm.last_prompt)

    def test_prompt_lists_the_full_allowed_action_vocabulary(self):
        llm = _CapturingLLM()
        self.agent._plan_via_llm(
            scenario={"scenario_id": "M03_BS_001", "title": "Scenario"},
            allowed_locators=[], test_data={}, base_url="http://x", flows_meta={}, llm=llm,
        )
        self.assertIn("verifyVisible", llm.last_prompt)
        self.assertIn("useFlow", llm.last_prompt)


if __name__ == "__main__":
    unittest.main()
