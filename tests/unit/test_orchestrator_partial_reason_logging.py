import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.orchestrator.agent import OrchestratorAgent
from workflows.workflow_loader import load_workflow
from agents.registry_setup import build_default_registry


class OrchestratorPartialReasonLoggingTests(unittest.TestCase):
    """A step that comes back status=partial (e.g. Discovery keeping a
    checkpointed DOM scan / comprehension result after a timeout) must have
    its reason actually printed, not silently treated like a plain success —
    that's the whole point of reporting 'partial' instead of 'failed'."""

    def test_partial_reasons_are_logged_as_warnings(self):
        settings = {"provider_mode": "external"}
        agents_config = {
            "agents": {
                "comprehension": {"enabled": True},
                "bdd": {"enabled": True},
                "testdata": {"enabled": True},
                "script_generation": {"enabled": True},
                "execution": {"enabled": True},
                "healing": {"enabled": True},
                "reporting": {"enabled": True},
            }
        }
        workflow = load_workflow("full_workflow")
        registry = build_default_registry()
        orchestrator = OrchestratorAgent(
            settings=settings, agents_config=agents_config, registry=registry, run_id="test-run-id",
        )
        request = {"workflow": "full_workflow", "message": "hello"}

        original = orchestrator._try_with_fallbacks

        def fake_try_with_fallbacks(step, req):
            if step == "discovery":
                return {"status": "partial", "partial_reasons": ["synthetic partial reason for test"]}
            return original(step, req)

        with patch.object(orchestrator, "_try_with_fallbacks", side_effect=fake_try_with_fallbacks), \
             patch.object(orchestrator.logger, "warning") as mock_warning:
            orchestrator.run(request, workflow)

        warned_messages = [call.args[0] for call in mock_warning.call_args_list]
        self.assertTrue(
            any("synthetic partial reason for test" in msg for msg in warned_messages),
            f"expected the partial reason to be logged, got: {warned_messages}",
        )

    def test_partial_without_partial_reasons_falls_back_to_error_field(self):
        settings = {"provider_mode": "external"}
        agents_config = {"agents": {}}
        workflow = load_workflow("full_workflow")
        registry = build_default_registry()
        orchestrator = OrchestratorAgent(
            settings=settings, agents_config=agents_config, registry=registry, run_id="test-run-id",
        )
        request = {"workflow": "full_workflow", "message": "hello"}

        original = orchestrator._try_with_fallbacks

        def fake_try_with_fallbacks(step, req):
            if step == "discovery":
                return {"status": "partial", "error": "fallback error text"}
            return original(step, req)

        with patch.object(orchestrator, "_try_with_fallbacks", side_effect=fake_try_with_fallbacks), \
             patch.object(orchestrator.logger, "warning") as mock_warning:
            orchestrator.run(request, workflow)

        warned_messages = [call.args[0] for call in mock_warning.call_args_list]
        self.assertTrue(any("fallback error text" in msg for msg in warned_messages))


if __name__ == "__main__":
    unittest.main()
