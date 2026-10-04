import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.orchestrator.agent import OrchestratorAgent
from agents.registry import AgentRegistry
from agents.registry_setup import LEGACY_AGENTS, build_default_registry
from contracts.state_models import WorkflowState
from workflows.workflow_loader import load_workflow


class _EchoAgent:
    """Stand-in for a real agent: records that it ran and echoes the step name."""

    calls = []

    def __init__(self, step: str, settings=None):
        self.step = step

    def execute(self, request, state):
        _EchoAgent.calls.append(self.step)
        return {"module": self.step, "status": "success", "response": f"hello back from {self.step}"}


def _echo_registry(steps):
    registry = AgentRegistry()
    for step in steps:
        registry.register(step, lambda settings=None, _s=step: _EchoAgent(_s, settings))
    return registry


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        _EchoAgent.calls = []

    def test_orchestrator_runs_all_full_workflow_steps_in_order(self):
        workflow = load_workflow("full_workflow")
        self.assertEqual(
            workflow.steps,
            ["discovery", "testdata", "semantic_map", "script_generation",
             "ui_execution", "healing", "reporting"],
        )
        settings = {
            "execution": {"ns": {"registry": "__none__.yaml", "agent_registry": "__none__.yaml"}},
        }
        orchestrator = OrchestratorAgent(
            settings=settings,
            agents_config={"agents": {s: {"enabled": True} for s in workflow.steps}},
            registry=_echo_registry(workflow.steps),
            run_id="test-run-id",
        )
        request = {"workflow": "full_workflow", "project_name": "orch_test",
                   "force_rediscover": True, "force_execute": True}

        with patch.object(OrchestratorAgent, "_llm_health_check", return_value=None):
            result = orchestrator.run(request, workflow)

        state = result["state"]
        self.assertIsInstance(state, WorkflowState)
        self.assertEqual(state.workflow_id, "full_workflow")
        self.assertEqual(state.run_id, "test-run-id")
        self.assertEqual(_EchoAgent.calls, workflow.steps)
        self.assertEqual(state.completed_steps[-1], "reporting")
        self.assertEqual(len(state.execution_trace), len(workflow.steps))
        self.assertEqual(state.execution_trace[-1]["step"], "reporting")
        self.assertEqual(state.outputs["discovery"]["response"], "hello back from discovery")
        self.assertEqual(result["final_report"]["status"], "success")

    def test_default_registry_covers_every_legacy_workflow_step(self):
        registry = build_default_registry(scope="legacy")
        for name in ("full_workflow", "test_comprehension_only", "test_test_creation_only",
                     "test_execution_only", "test_execution_and_healing", "healing_only"):
            for step in load_workflow(name).steps:
                self.assertIn(step, registry, f"{name}: step '{step}' is not registered")
        self.assertEqual(len(registry), len(LEGACY_AGENTS))


if __name__ == "__main__":
    unittest.main()
