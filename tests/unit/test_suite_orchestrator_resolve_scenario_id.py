import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.suite_orchestrator import resolve_suite_spec_files


class ResolveSuiteSpecFilesTests(unittest.TestCase):
    """resolve_suite_spec_files() backs the current, project-agnostic
    `python main.py --suite <name>` path (not the legacy cli_appevolve.py
    tool). It must resolve every spec_id scheme script_generation has ever
    used — legacy hyphenated ("BS-001") and the current module-scoped
    underscore scheme ("M03_BS_006") — not just the legacy one."""

    def setUp(self):
        self.project_dir = tempfile.mkdtemp()
        scripts_root = os.path.join(self.project_dir, "test_creation", "test_scripts", "M03")
        os.makedirs(scripts_root, exist_ok=True)
        for fname in ["test_BS-001_legacy.spec.ts", "test_M03_BS_006_verify_page_title.spec.ts"]:
            with open(os.path.join(scripts_root, fname), "w", encoding="utf-8") as f:
                f.write("// spec")

        suite_manifest = os.path.join(self.project_dir, "test_creation", "test_suite.json")
        with open(suite_manifest, "w", encoding="utf-8") as f:
            json.dump({"specs": [
                {"spec_id": "BS-001", "module_id": "M03", "file": "M03/test_BS-001_legacy.spec.ts"},
                {"spec_id": "M03_BS_006", "module_id": "M03", "file": "M03/test_M03_BS_006_verify_page_title.spec.ts"},
            ]}, f)

        suites_dir = os.path.join(self.project_dir, "test_suites")
        os.makedirs(suites_dir, exist_ok=True)
        self.suites_dir = suites_dir

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def _write_suite(self, scenarios):
        with open(os.path.join(self.suites_dir, "smoke_suite.json"), "w", encoding="utf-8") as f:
            json.dump({"suite_id": "smoke", "scenarios": scenarios}, f)

    def test_resolves_legacy_hyphenated_id(self):
        self._write_suite(["BS-001"])
        resolved = resolve_suite_spec_files(self.project_dir, "smoke")
        self.assertEqual(len(resolved), 1)
        self.assertTrue(str(resolved[0]["path"]).endswith("test_BS-001_legacy.spec.ts"))

    def test_resolves_module_scoped_underscore_id(self):
        self._write_suite(["M03_BS_006"])
        resolved = resolve_suite_spec_files(self.project_dir, "smoke")
        self.assertEqual(len(resolved), 1)
        self.assertTrue(str(resolved[0]["path"]).endswith("test_M03_BS_006_verify_page_title.spec.ts"))

    def test_unknown_id_resolves_to_empty(self):
        self._write_suite(["M99_BS_999"])
        resolved = resolve_suite_spec_files(self.project_dir, "smoke")
        self.assertEqual(resolved, [])

    def test_mixed_scheme_scenarios_all_resolve(self):
        self._write_suite(["BS-001", "M03_BS_006"])
        resolved = resolve_suite_spec_files(self.project_dir, "smoke")
        self.assertEqual(len(resolved), 2)


if __name__ == "__main__":
    unittest.main()
