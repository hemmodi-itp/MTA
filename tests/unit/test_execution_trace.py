import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from contracts.state_models import WorkflowState


class ExecutionTraceTests(unittest.TestCase):
    def test_start_and_finish_step_trace(self):
        state = WorkflowState(run_id="trace-run", workflow_id="trace", workflow_name="trace")
        state.start_step("comprehension")
        state.finish_step("comprehension", status="success")

        self.assertEqual(len(state.execution_trace), 1)
        trace = state.execution_trace[0]
        self.assertEqual(trace["step"], "comprehension")
        self.assertEqual(trace["status"], "success")
        self.assertTrue(trace["duration_ms"] >= 0)


if __name__ == "__main__":
    unittest.main()
