import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.orchestrator.agent import OrchestratorAgent
from agents.registry import AgentRegistry
from contracts.state_models import WorkflowState


class FailingAgent:
    def __init__(self, provider=None, settings=None):
        pass

    def execute(self, request: dict, state: dict):
        raise RuntimeError("Failure in agent")


class WorkflowDefinition:
    def __init__(self):
        self.workflow_id = "error_workflow"
        self.steps = ["failing"]


class ErrorHandlingTests(unittest.TestCase):
    def test_workflow_records_error_and_continues(self):
        registry = AgentRegistry()
        registry.register("failing", FailingAgent)

        settings = {"providers": {} }
        agents_config = {"agents": {"failing": {"enabled": True}}}
        orchestrator = OrchestratorAgent(
            settings=settings,
            agents_config=agents_config,
            registry=registry,
            run_id="error-run",
        )
        result = orchestrator.run({"workflow": "error_workflow", "message": "hello"}, WorkflowDefinition())

        self.assertEqual(result["state"].workflow_id, "error_workflow")
        self.assertEqual(result["state"].run_id, "error-run")
        # index by step name, not position — the mandatory llm_health_check
        # pre-flight step (using the mock LLM connector here) now runs first
        failing_trace = next(
            e for e in result["state"].execution_trace if e["step"] == "failing"
        )
        self.assertEqual(failing_trace["status"], "failed")
        self.assertEqual(result["state"].errors[0]["step"], "failing")
        self.assertEqual(result["final_report"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
