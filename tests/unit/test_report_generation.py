import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.file_manager import save_json_file, load_json_file
from tools.report_writer import build_final_report


class ReportGenerationTests(unittest.TestCase):
    def test_build_and_write_report(self):
        outputs = {
            "comprehension": {"response": "hello back from comprehension"},
            "bdd": {"response": "hello back from bdd"},
            "testdata": {"response": "hello back from testdata"},
            "script_generation": {"response": "hello back from script_generation"},
            "execution": {"response": "hello back from execution"},
            "healing": {"response": "hello back from healing"},
        }
        report = build_final_report(
            run_id="test-run-id",
            workflow_name="full_workflow",
            status="success",
            steps_executed=[
                "comprehension",
                "bdd",
                "testdata",
                "script_generation",
                "execution",
                "healing",
                "reporting",
            ],
            outputs=outputs,
            execution_trace=[],
            errors=[],
        )
        self.assertEqual(report["workflow"], "full_workflow")
        self.assertEqual(report["status"], "success")
        self.assertIn("comprehension", report["responses"])

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "final_report.json")
            save_json_file(path, report)
            loaded = load_json_file(path)
            self.assertEqual(loaded["workflow"], "full_workflow")
            self.assertEqual(loaded["responses"]["execution"], "hello back from execution")


if __name__ == "__main__":
    unittest.main()
