import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.comprehension.discovery.agent import DiscoveryAgent


class PromoteDomCheckpointTests(unittest.TestCase):
    """A DOM scan abandoned by the outer timeout must still leave real,
    usable dom_elements.json/dom_intents.json artifacts behind if it had
    already collected anything before the deadline, instead of the pipeline
    losing that work entirely."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        p = patch("agents.comprehension.discovery.agent._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)
        self.agent = DiscoveryAgent()

    def _checkpoint_path(self, safe="proj", module_id=None):
        request = {"module_filter": module_id} if module_id else {}
        return self.agent._dom_checkpoint_path(request, safe)

    def _write_checkpoint(self, path, elements, url="https://example.com"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"url": url, "title": "Home", "elements": elements, "partial": True}, f)

    def test_no_checkpoint_file_returns_none(self):
        result = self.agent._promote_dom_checkpoint(
            self._checkpoint_path(), {"project_name": "proj"}, "proj"
        )
        self.assertIsNone(result)

    def test_empty_checkpoint_returns_none(self):
        path = self._checkpoint_path()
        self._write_checkpoint(path, [])
        result = self.agent._promote_dom_checkpoint(path, {"project_name": "proj"}, "proj")
        self.assertIsNone(result)

    def test_corrupt_checkpoint_returns_none(self):
        path = self._checkpoint_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        result = self.agent._promote_dom_checkpoint(path, {"project_name": "proj"}, "proj")
        self.assertIsNone(result)

    def test_checkpoint_with_elements_writes_real_artifacts(self):
        path = self._checkpoint_path()
        elements = [{
            "locator_id": "LOC-0001",
            "tag": "button",
            "technical_locators": {"css": "#submit"},
            "semantic_locators": {"role": "button"},
        }]
        self._write_checkpoint(path, elements)

        result = self.agent._promote_dom_checkpoint(path, {"project_name": "proj"}, "proj")

        self.assertIsNotNone(result)
        self.assertEqual(result["dom_status"], "partial")
        self.assertTrue(os.path.exists(result["dom_elements_path"]))
        self.assertTrue(os.path.exists(result["dom_intents_path"]))
        self.assertGreaterEqual(result["dom_intents_count"], 0)
        self.assertIn("dom_intents_raw", result)


class PromoteComprehensionPartialTests(unittest.TestCase):
    """Comprehension's per-module incremental export (see ComprehensionAgent
    ._execute_modular) means an abandoned comprehension thread may already
    have written real scenarios before the deadline — this must be detected
    and kept, but only if it's fresh (written during THIS run), not stale
    leftovers from a previous run."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        p = patch("agents.comprehension.discovery.agent._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)
        self.agent = DiscoveryAgent()
        self.comp_dir = os.path.join(self.tmp_dir, "proj", "test_comprehension")
        os.makedirs(self.comp_dir, exist_ok=True)
        self.bs_path = os.path.join(self.comp_dir, "business_scenarios.json")

    def _write_scenarios(self, count):
        with open(self.bs_path, "w", encoding="utf-8") as f:
            json.dump({"total_scenarios": count, "scenarios": [{}] * count}, f)

    def test_no_file_returns_none(self):
        result = self.agent._promote_comprehension_partial("proj", None)
        self.assertIsNone(result)

    def test_unchanged_mtime_returns_none(self):
        self._write_scenarios(2)
        mtime_before = os.path.getmtime(self.bs_path)
        result = self.agent._promote_comprehension_partial("proj", mtime_before)
        self.assertIsNone(result)

    def test_fresh_write_after_snapshot_is_promoted(self):
        mtime_before = time.time() - 100  # snapshot predates the write below
        self._write_scenarios(3)
        result = self.agent._promote_comprehension_partial("proj", mtime_before)
        self.assertIsNotNone(result)
        self.assertEqual(result["scenarios_count"], 3)
        self.assertEqual(result["comprehension_source"], "partial_checkpoint")

    def test_no_prior_snapshot_treats_any_existing_file_as_fresh(self):
        self._write_scenarios(1)
        result = self.agent._promote_comprehension_partial("proj", None)
        self.assertIsNotNone(result)
        self.assertEqual(result["scenarios_count"], 1)


class RunBothTimeoutPromotesPartialDataTests(unittest.TestCase):
    """End-to-end through _run_both: a scan that times out but left a
    checkpoint must report status=partial (with real files written and a
    reason recorded), not status=failed with nothing to show for it."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        p = patch("agents.comprehension.discovery.agent._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)
        self.agent = DiscoveryAgent()
        self.agent._run_comprehension = lambda *a, **kw: {"comprehension_status": "success"}
        self.agent._save_intents_yaml = lambda **kw: "fake/intents.yaml"

    def test_wedged_scan_with_checkpoint_reports_partial_not_failed(self):
        never_set = threading.Event()
        request = {"discovery_timeout_s": 0.2, "project_name": "proj"}
        checkpoint_path = self.agent._dom_checkpoint_path(request, "proj")
        os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump({
                "url": "https://example.com",
                "elements": [{
                    "locator_id": "LOC-0001",
                    "tag": "button",
                    "technical_locators": {"css": "#submit"},
                }],
            }, f)

        def wedged_scan(*_a, **_kw):
            never_set.wait()
            return {"dom_status": "success"}  # unreachable

        self.agent._run_dom_scan = wedged_scan

        result = self.agent._run_both(request, {}, "proj")

        self.assertEqual(result["dom_status"], "partial")
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any("timed out" in r for r in result["partial_reasons"]))
        self.assertTrue(os.path.exists(result["dom_elements_path"]))


if __name__ == "__main__":
    unittest.main()
