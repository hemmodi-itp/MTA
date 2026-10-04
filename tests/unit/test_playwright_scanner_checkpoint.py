import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.playwright_scanner import write_scan_checkpoint


class WriteScanCheckpointTests(unittest.TestCase):
    """write_scan_checkpoint is the mechanism that lets a caller-side timeout
    (DiscoveryAgent's 60s join) promote whatever elements a headless DOM scan
    had already collected instead of discarding them — see
    DiscoveryAgent._promote_dom_checkpoint."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.checkpoint_path = os.path.join(self.tmp_dir, ".dom_scan_checkpoint.json")

    def test_writes_elements_url_and_partial_marker(self):
        elements = [{"locator_id": "LOC-0001", "tag": "button"}]
        write_scan_checkpoint(self.checkpoint_path, "https://example.com", "Home", elements)

        with open(self.checkpoint_path, encoding="utf-8") as f:
            doc = json.load(f)

        self.assertEqual(doc["url"], "https://example.com")
        self.assertEqual(doc["title"], "Home")
        self.assertEqual(doc["elements"], elements)
        self.assertEqual(doc["element_count"], 1)
        self.assertTrue(doc["partial"])

    def test_no_tmp_file_left_behind_after_write(self):
        write_scan_checkpoint(self.checkpoint_path, "https://example.com", "Home", [])
        self.assertFalse(os.path.exists(self.checkpoint_path + ".tmp"))
        self.assertTrue(os.path.exists(self.checkpoint_path))

    def test_second_write_overwrites_first(self):
        write_scan_checkpoint(self.checkpoint_path, "https://example.com", "Home", [{"a": 1}])
        write_scan_checkpoint(self.checkpoint_path, "https://example.com", "Home", [{"a": 1}, {"a": 2}])

        with open(self.checkpoint_path, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["element_count"], 2)


if __name__ == "__main__":
    unittest.main()
