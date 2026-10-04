import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.comprehension.discovery.agent import DiscoveryAgent


class MandatoryOutputGateInteractiveTests(unittest.TestCase):
    """A fully-failed or empty interactive scan must block the workflow
    (status=failed) instead of silently reporting "partial" — the exact gap
    that let the M04 bug go unnoticed (dom_status=failed but the mandatory
    gate never checked DOM artifacts at all)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        p = patch("agents.comprehension.discovery.agent._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)
        self.agent = DiscoveryAgent()
        self._write_business_scenarios()
        self._write_intents_yaml()

    def _write_business_scenarios(self):
        comp_dir = os.path.join(self.tmp_dir, "proj", "test_comprehension")
        os.makedirs(comp_dir, exist_ok=True)
        with open(os.path.join(comp_dir, "business_scenarios.json"), "w", encoding="utf-8") as f:
            json.dump({"scenarios": []}, f)
        with open(os.path.join(comp_dir, "business_scenarios.md"), "w", encoding="utf-8") as f:
            f.write("# scenarios")

    def _write_intents_yaml(self):
        tc_dir = os.path.join(self.tmp_dir, "proj", "test_creation")
        os.makedirs(tc_dir, exist_ok=True)
        with open(os.path.join(tc_dir, "intents.yaml"), "w", encoding="utf-8") as f:
            f.write("project: proj\nintents: []\n")

    def _write_dom_elements(self, module_id, elements):
        comp_root = os.path.join(self.tmp_dir, "proj", "test_comprehension")
        scan_dir = os.path.join(comp_root, "modules", module_id) if module_id else comp_root
        os.makedirs(scan_dir, exist_ok=True)
        with open(os.path.join(scan_dir, "dom_elements.json"), "w", encoding="utf-8") as f:
            json.dump({"elements": elements, "total_element_count": len(elements)}, f)

    def test_missing_dom_elements_fails_when_interactive(self):
        missing = self.agent._check_mandatory_outputs("both", "proj", "M04", interactive=True)
        self.assertIn("dom_elements.json", missing)

    def test_empty_dom_elements_fails_when_interactive(self):
        self._write_dom_elements("M04", [])
        missing = self.agent._check_mandatory_outputs("both", "proj", "M04", interactive=True)
        self.assertIn("dom_elements.json", missing)

    def test_nonempty_dom_elements_passes_when_interactive(self):
        self._write_dom_elements("M04", [{"locator_id": "LOC-0001"}])
        missing = self.agent._check_mandatory_outputs("both", "proj", "M04", interactive=True)
        self.assertNotIn("dom_elements.json", missing)
        self.assertEqual(missing, [])

    def test_dom_elements_not_required_when_not_interactive(self):
        # Non-interactive (headless) scans are unaffected by this gate addition —
        # today's behavior for automated scans must not change.
        missing = self.agent._check_mandatory_outputs("both", "proj", None, interactive=False)
        self.assertNotIn("dom_elements.json", missing)

    def test_missing_dom_elements_not_checked_for_brd_only_mode(self):
        missing = self.agent._check_mandatory_outputs("brd_only", "proj", "M04", interactive=True)
        self.assertNotIn("dom_elements.json", missing)

    def test_execute_reports_failed_not_partial_for_empty_interactive_scan(self):
        self._write_dom_elements("M04", [])
        self.agent._run_both = lambda request, state, safe: {
            "status": "partial", "comprehension_status": "success",
            "dom_status": "success", "dom_intents_raw": [], "intents_path": "x",
        }

        result = self.agent.execute(
            {
                "project_name": "proj", "url": "https://x", "brd_dir": self.tmp_dir,
                "interactive_scan": True, "module_filter": "M04",
            },
            {},
        )

        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["blocking"])
        self.assertIn("dom_elements.json", result["missing_outputs"])


if __name__ == "__main__":
    unittest.main()
