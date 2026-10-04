import logging
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import ScriptGenerationAgent


def _registry_settings(tmp_dir, python_stub_enabled):
    # Every fallback tier ships disabled by default (workflows/agent_registry.yaml) —
    # a connector_type entry alone is not enough, it must also carry enabled: true.
    path = os.path.join(tmp_dir, "agent_registry.yaml")
    if python_stub_enabled:
        body = (
            "agents:\n"
            "  script_generation:\n"
            "    connector_type: internal\n"
            "    fallbacks:\n"
            "      - connector_type: python_stub\n"
            "        fallback_module: agents.common.fallback_core\n"
            "        enabled: true\n"
        )
    else:
        body = "agents:\n  script_generation:\n    connector_type: internal\n    fallbacks: []\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return {"execution": {"ns": {"agent_registry": path}}}


def _agent_with_failing_llm(settings):
    agent = ScriptGenerationAgent(settings=settings)
    fake_llm = MagicMock()
    fake_llm.generate.side_effect = RuntimeError("provider unreachable")
    agent._registry = MagicMock()
    agent._registry.get_llm.return_value = fake_llm
    return agent


class ScriptGenerationStubFallbackToggleTests(unittest.TestCase):
    def test_stub_fallback_disabled_raises_instead_of_generating_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _registry_settings(tmp, python_stub_enabled=False)
            agent = _agent_with_failing_llm(settings)

            with self.assertRaises(RuntimeError) as ctx:
                agent._generate_spec(
                    request={},
                    scenario={"scenario_id": "M03_BS_099", "title": "Unreachable scenario"},
                    allowed_locators=[],
                    test_data={},
                    base_url="https://example.com",
                    flows_meta={},
                )
            self.assertIn("stub fallback is disabled", str(ctx.exception))
            self.assertIn("provider unreachable", str(ctx.exception))

    def test_retry_log_line_includes_underlying_exception_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _registry_settings(tmp, python_stub_enabled=False)
            agent = _agent_with_failing_llm(settings)

            with self.assertLogs("agent.script_generation", level="WARNING") as ctx:
                with self.assertRaises(RuntimeError):
                    agent._generate_spec(
                        request={},
                        scenario={"scenario_id": "M03_BS_099", "title": "Unreachable scenario"},
                        allowed_locators=[],
                        test_data={},
                        base_url="https://example.com",
                        flows_meta={},
                    )
            self.assertTrue(any("provider unreachable" in line for line in ctx.output))

    def test_stub_fallback_enabled_returns_tier_2_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = _registry_settings(tmp, python_stub_enabled=True)
            agent = _agent_with_failing_llm(settings)

            kind, payload, tier_used, fallback_route = agent._generate_spec(
                request={},
                scenario={"scenario_id": "M03_BS_099", "title": "Unreachable scenario"},
                allowed_locators=[],
                test_data={},
                base_url="https://example.com",
                flows_meta={},
            )
            self.assertEqual(kind, "raw")
            self.assertEqual(tier_used, 2)
            self.assertTrue(payload.strip())


if __name__ == "__main__":
    unittest.main()
