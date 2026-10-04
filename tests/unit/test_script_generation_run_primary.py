import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import ScriptGenerationAgent


class RunPrimaryDelegatesToExecuteTests(unittest.TestCase):
    """ScriptGenerationAgent used to override _run_primary with a call to a
    nonexistent self._execute_inner — unreachable today (nothing calls
    execute_with_fallback on this agent) but a landmine if that ever changes.
    BaseAgent's default _run_primary (self.execute(request, state)) is
    already correct here, so the override was removed rather than fixed."""

    def test_run_primary_delegates_to_execute(self):
        agent = ScriptGenerationAgent(settings={})
        agent.execute = MagicMock(return_value={"module": "script_generation", "status": "success"})

        request = {"project_name": "proj"}
        state = {}
        result = agent._run_primary(request, state)

        agent.execute.assert_called_once_with(request, state)
        self.assertEqual(result, {"module": "script_generation", "status": "success"})

    def test_execute_inner_is_not_referenced(self):
        agent = ScriptGenerationAgent(settings={})
        self.assertFalse(hasattr(agent, "_execute_inner"))


if __name__ == "__main__":
    unittest.main()
