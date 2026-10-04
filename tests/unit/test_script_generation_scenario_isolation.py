import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import ScriptGenerationAgent

_PLAN = json.dumps({
    "tests": [
        {
            "name": "positive — x",
            "type": "positive",
            "steps": [
                {"action": "navigate"},
                {"action": "verifyUrl", "value": "https://example.com", "message": "lands on example"},
            ],
        }
    ],
    "missing_actions": [],
    "missing_locators": [],
})


class _StubLLM:
    def generate(self, prompt: str) -> str:
        return _PLAN


class PostGenerationFailureIsolationTests(unittest.TestCase):
    """A failure that happens AFTER _generate_spec returns (rendering, disk
    write, catalog/suite bookkeeping) must be isolated to that one scenario,
    the same way a _generate_spec failure already is — a bug here is exactly
    what let one bad scenario's KeyError('value') take down an entire
    script_generation run (and, downstream, the whole workflow) instead of
    being skipped and logged like every other per-scenario failure."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.tmp_dir, "proj")
        comp_dir = os.path.join(self.project_dir, "test_comprehension")
        os.makedirs(comp_dir, exist_ok=True)
        with open(os.path.join(comp_dir, "business_scenarios.json"), "w", encoding="utf-8") as f:
            json.dump({"scenarios": [
                {"scenario_id": "SC-001", "title": "First scenario", "module_id": "M01"},
                {"scenario_id": "SC-002", "title": "Second scenario", "module_id": "M01"},
            ]}, f)

        os.makedirs(os.path.join(self.project_dir, "test_creation"), exist_ok=True)

        self.agent = ScriptGenerationAgent(settings={})
        self.agent._registry.get_llm = MagicMock(return_value=_StubLLM())

        self._patch_base = patch(
            "agents.test_creation.script_generation.agent._ASSETS_BASE", self.tmp_dir
        )
        self._patch_base.start()

    def tearDown(self):
        self._patch_base.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_render_failure_on_one_scenario_does_not_abort_the_others(self):
        request = {"project_name": "proj", "module_filter": "M01"}

        real_render = __import__(
            "agents.test_creation.script_generation.agent", fromlist=["render_spec_from_plan"]
        ).render_spec_from_plan

        def _boom_for_second_scenario(plan, scenario, *args, **kwargs):
            if scenario.get("scenario_id") == "SC-002":
                raise KeyError("value")
            return real_render(plan, scenario, *args, **kwargs)

        with patch(
            "agents.test_creation.script_generation.agent.render_spec_from_plan",
            side_effect=_boom_for_second_scenario,
        ):
            out = self.agent.execute(request, {})

        self.assertEqual(out["status"], "partial")
        self.assertEqual(out["scripts_generated"], 1)
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIn("SC-002", out["warnings"][0])


if __name__ == "__main__":
    unittest.main()
