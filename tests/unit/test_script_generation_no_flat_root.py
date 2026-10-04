import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import ScriptGenerationAgent, _resolve_target_module_id

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


class ResolveTargetModuleIdTests(unittest.TestCase):
    """The routing decision, in isolation from execute()'s side effects."""

    def test_scenario_module_id_wins(self):
        self.assertEqual(_resolve_target_module_id("M02", {"module_filter": "M03"}), "M02")

    def test_falls_back_to_module_filter(self):
        self.assertEqual(_resolve_target_module_id(None, {"module_filter": "M03"}), "M03")

    def test_falls_back_to_first_declared_module_when_no_filter(self):
        request = {"modules": [{"id": "M01", "url": "https://example.com"}]}
        self.assertEqual(_resolve_target_module_id(None, request), "M01")

    def test_none_when_no_module_context_at_all(self):
        self.assertIsNone(_resolve_target_module_id(None, {}))


class ScriptGenerationNeverWritesFlatTests(unittest.TestCase):
    """A scenario with no module_id must still land under a module folder —
    test_scripts/ must never receive a flat, non-module spec file again."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.tmp_dir, "proj")
        comp_dir = os.path.join(self.project_dir, "test_comprehension")
        os.makedirs(comp_dir, exist_ok=True)
        with open(os.path.join(comp_dir, "business_scenarios.json"), "w", encoding="utf-8") as f:
            json.dump({"scenarios": [
                {"scenario_id": "SC-001", "title": "Legacy scenario", "module_id": None},
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

    def _flat_scripts_dir(self):
        return os.path.join(self.project_dir, "test_creation", "test_scripts")

    def test_no_module_id_scenario_adopts_active_module_filter(self):
        request = {"project_name": "proj", "module_filter": "M03"}
        out = self.agent.execute(request, {})

        self.assertEqual(out["scripts_generated"], 1)
        flat_dir = self._flat_scripts_dir()
        flat_files = [f for f in os.listdir(flat_dir) if f.endswith(".spec.ts")]
        self.assertEqual(flat_files, [], "no .spec.ts file may be written directly into test_scripts/")

        module_dir = os.path.join(flat_dir, "M03")
        module_files = [f for f in os.listdir(module_dir) if f.endswith(".spec.ts")]
        self.assertEqual(len(module_files), 1)

        with open(os.path.join(self.project_dir, "test_creation", "test_suite.json"), encoding="utf-8") as f:
            suite = json.load(f)
        self.assertEqual(suite["specs"][0]["module_id"], "M03")
        self.assertEqual(suite["specs"][0]["file"], f"M03/{module_files[0]}")

    def test_no_module_context_skips_scenario_without_writing_flat(self):
        request = {"project_name": "proj"}  # no module_filter, no modules[]
        out = self.agent.execute(request, {})

        self.assertEqual(out["scripts_generated"], 0)
        self.assertEqual(len(out["warnings"]), 1)
        self.assertIn("no module context available", out["warnings"][0])

        flat_dir = self._flat_scripts_dir()
        if os.path.isdir(flat_dir):
            flat_files = [f for f in os.listdir(flat_dir) if f.endswith(".spec.ts")]
            self.assertEqual(flat_files, [])


if __name__ == "__main__":
    unittest.main()
