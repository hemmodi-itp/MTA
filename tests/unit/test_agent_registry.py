import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.registry import AgentRegistry


class AgentRegistryTests(unittest.TestCase):
    def test_register_and_get_agent(self):
        registry = AgentRegistry()

        class DummyAgent:
            def __init__(self, provider=None, settings=None):
                self.provider = provider
                self.settings = settings

        registry.register("dummy", DummyAgent)
        agent_cls = registry.get("dummy")
        self.assertIs(agent_cls, DummyAgent)
        agent = registry.build("dummy", provider="provider", settings={"key": "value"})
        self.assertIsInstance(agent, DummyAgent)
        self.assertEqual(agent.provider, "provider")
        self.assertEqual(agent.settings, {"key": "value"})

    def test_missing_agent_raises_key_error(self):
        registry = AgentRegistry()
        with self.assertRaises(KeyError):
            registry.get("missing")


# Keys api/pipeline.py dispatches for workflows/agent_evaluation.yaml.
_MTA_KEYS = {
    "repo_fetch", "repo_analysis", "repo_intelligence", "brd_builder", "agent_test_generation",
    "runtime_discovery", "app_classification", "action_generation", "playwright_executor",
    "evidence_collection", "output_validation", "pass_fail", "live_agent_execution",
    "requirement_traceability", "repository_review", "brd_compliance", "compliance_scoring",
    "final_report",
}


class LazyRegistryTests(unittest.TestCase):
    def test_lazy_entry_imports_only_on_build(self):
        registry = AgentRegistry()
        registry.register_lazy("od", "collections", "OrderedDict")
        self.assertIn("od", registry)
        self.assertIsNotNone(registry.spec("od"))
        built = registry.build("od", a=1)
        self.assertEqual(dict(built), {"a": 1})
        self.assertIsNone(registry.spec("od"))  # loaded + cached

    def test_lazy_entry_binds_constructor_kwargs(self):
        registry = AgentRegistry()
        registry.register_lazy("ctr", "collections", "Counter", a=2)
        self.assertEqual(registry.build("ctr")["a"], 2)

    def test_broken_lazy_entry_fails_only_that_key(self):
        registry = AgentRegistry()
        registry.register_lazy("broken", "agents.does_not_exist.agent", "Nope")
        registry.register_lazy("ok", "collections", "OrderedDict")
        self.assertIsNotNone(registry.build("ok"))
        with self.assertRaises(ImportError):
            registry.build("broken")

    def test_default_registry_scopes(self):
        from agents.registry_setup import build_default_registry
        mta = set(build_default_registry(scope="mta").keys())
        legacy = set(build_default_registry(scope="legacy").keys())
        self.assertEqual(mta, _MTA_KEYS)
        self.assertTrue({"discovery", "script_generation", "ui_execution", "reporting"} <= legacy)
        self.assertFalse(mta & legacy)
        self.assertEqual(set(build_default_registry().keys()), mta | legacy)
        with self.assertRaises(ValueError):
            build_default_registry(scope="nope")

    def test_building_the_registry_imports_no_agent_module(self):
        code = (
            "import json, sys; "
            "from agents.registry_setup import build_default_registry; "
            "build_default_registry(); "
            "mods = [m for m in sys.modules if m.startswith('agents.') and m.endswith('.agent')]; "
            "print(json.dumps(mods))"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout
        self.assertEqual(json.loads(out.strip().splitlines()[-1]), [])

    def test_every_mta_agent_builds(self):
        from agents.registry_setup import build_default_registry
        registry = build_default_registry(scope="mta")
        for key in sorted(_MTA_KEYS):
            self.assertTrue(callable(registry.get(key)), key)


if __name__ == "__main__":
    unittest.main()
