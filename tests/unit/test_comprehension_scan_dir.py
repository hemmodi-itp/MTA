import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.discovery.paths import comprehension_scan_dir
from tools.state import project_state_manager as psm


class ComprehensionScanDirTests(unittest.TestCase):
    """Single source of truth for module-scoped DOM/interactive scan paths —
    every writer/reader in the restructure routes through this function so
    module M04's scan can never overwrite M01's again."""

    def test_module_id_scopes_under_modules_subdir(self):
        self.assertEqual(
            comprehension_scan_dir(os.path.join("proj", "comprehension"), "M04"),
            os.path.join("proj", "comprehension", "modules", "M04"),
        )

    def test_no_module_id_returns_root_unchanged(self):
        root = os.path.join("proj", "comprehension")
        self.assertEqual(comprehension_scan_dir(root, None), root)
        self.assertEqual(comprehension_scan_dir(root, ""), root)

    def test_different_modules_scope_to_different_dirs(self):
        root = os.path.join("proj", "comprehension")
        m01 = comprehension_scan_dir(root, "M01")
        m04 = comprehension_scan_dir(root, "M04")
        self.assertNotEqual(m01, m04)


class ComputeDomFingerprintModuleScopingTests(unittest.TestCase):
    """compute_dom_fingerprint must hash the module-scoped file when a
    module_id is given — the exact regression this restructure was verified
    against (the impact audit found this as a previously-unaccounted-for
    consumer of the flat comprehension/dom_elements.json path)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        import unittest.mock as mock
        p = mock.patch("tools.state.project_state_manager._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)

    def _write_dom_elements(self, module_id, content):
        comp_root = os.path.join(self.tmp_dir, "proj", "test_comprehension")
        scan_dir = comprehension_scan_dir(comp_root, module_id)
        os.makedirs(scan_dir, exist_ok=True)
        with open(os.path.join(scan_dir, "dom_elements.json"), "w", encoding="utf-8") as f:
            f.write(content)

    def test_empty_string_when_module_scoped_file_missing(self):
        self.assertEqual(psm.compute_dom_fingerprint("proj", "M04"), "")

    def test_fingerprints_module_scoped_file_when_module_id_given(self):
        self._write_dom_elements("M04", '{"elements": []}')
        fp = psm.compute_dom_fingerprint("proj", "M04")
        self.assertTrue(fp.startswith("sha256:"))

    def test_m01_and_m04_fingerprints_are_independent(self):
        self._write_dom_elements("M01", '{"elements": [1]}')
        self._write_dom_elements("M04", '{"elements": [1, 2]}')

        fp01 = psm.compute_dom_fingerprint("proj", "M01")
        fp04 = psm.compute_dom_fingerprint("proj", "M04")

        self.assertNotEqual(fp01, fp04)

        # Changing M04's file must not affect M01's fingerprint — this is the
        # exact skip-discovery-if-unchanged correctness bug that a flat,
        # non-module-scoped path would silently reintroduce.
        self._write_dom_elements("M04", '{"elements": [1, 2, 3]}')
        self.assertEqual(psm.compute_dom_fingerprint("proj", "M01"), fp01)
        self.assertNotEqual(psm.compute_dom_fingerprint("proj", "M04"), fp04)

    def test_no_module_id_falls_back_to_flat_layout(self):
        self._write_dom_elements(None, '{"elements": []}')
        fp = psm.compute_dom_fingerprint("proj")
        self.assertTrue(fp.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
