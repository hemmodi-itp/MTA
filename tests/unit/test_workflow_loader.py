import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from workflows.workflow_loader import load_workflow


class WorkflowLoaderTests(unittest.TestCase):
    def test_load_full_workflow(self):
        workflow = load_workflow("full_workflow")
        self.assertEqual(workflow.workflow_id, "full_workflow")
        self.assertEqual(
            workflow.steps,
            [
                "discovery",
                "testdata",
                "semantic_map",
                "script_generation",
                "ui_execution",
                "healing",
                "reporting",
            ],
        )
        self.assertEqual(workflow.always_run, {"reporting"})

    def test_load_test_comprehension_only(self):
        workflow = load_workflow("test_comprehension_only")
        self.assertEqual(workflow.steps, ["discovery"])

    def test_load_test_test_creation_only(self):
        workflow = load_workflow("test_test_creation_only")
        self.assertEqual(workflow.steps, ["testdata", "semantic_map", "script_generation"])

    def test_load_test_execution_only(self):
        workflow = load_workflow("test_execution_only")
        self.assertEqual(workflow.steps, ["ui_execution", "reporting"])
        self.assertEqual(workflow.always_run, {"reporting"})

    def test_load_healing_only(self):
        workflow = load_workflow("healing_only")
        self.assertEqual(workflow.steps, ["healing", "reporting"])
        self.assertEqual(workflow.always_run, {"reporting"})

    def test_load_test_execution_and_healing(self):
        workflow = load_workflow("test_execution_and_healing")
        self.assertEqual(workflow.steps, ["ui_execution", "healing", "reporting"])
        self.assertEqual(workflow.always_run, {"reporting"})

    def test_retired_workflows_no_longer_exist(self):
        for name in ("ns_workflow", "execution_only", "execution_and_healing"):
            with self.assertRaises(FileNotFoundError):
                load_workflow(name)


if __name__ == "__main__":
    unittest.main()
