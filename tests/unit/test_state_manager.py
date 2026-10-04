import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from contracts.state_models import WorkflowState


class StateManagerTests(unittest.TestCase):
    def test_state_updates(self):
        state = WorkflowState()
        state.update_step("comprehension", {"module": "comprehension", "response": "hello"})
        self.assertEqual(state.workflow_id, "")
        self.assertEqual(state.current_step, "comprehension")
        self.assertEqual(state.completed_steps, ["comprehension"])
        self.assertIn("comprehension", state.outputs)
        self.assertEqual(state.outputs["comprehension"]["response"], "hello")


if __name__ == "__main__":
    unittest.main()
