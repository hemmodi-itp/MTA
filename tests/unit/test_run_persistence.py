import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.persistence import save_workflow_run, load_workflow_run


class PersistenceTests(unittest.TestCase):
    def test_save_and_load_workflow_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            payload = {
                "run_id": "persist-run",
                "workflow": "full_workflow",
                "status": "success",
                "execution_trace": [],
                "errors": [],
            }
            original_dir = os.getcwd()
            try:
                os.chdir(temp_dir)
                save_workflow_run("persist-run", payload, base_dir=temp_dir)
                loaded = load_workflow_run("persist-run", base_dir=temp_dir)
                self.assertEqual(loaded["run_id"], "persist-run")
                self.assertEqual(loaded["workflow"], "full_workflow")
            finally:
                os.chdir(original_dir)


if __name__ == "__main__":
    unittest.main()
