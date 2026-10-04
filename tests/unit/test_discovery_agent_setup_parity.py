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

_SETUP_STEPS = [{"goto": "https://app.example/login"}, {"click": "#sso"}]
_AUTH = {"strategy": "live_login"}


def _dummy_headless_result():
    return {"elements": [], "element_count": 0}


class DiscoveryAgentSetupParityTests(unittest.TestCase):
    """Headless DOM scans still resolve auth/setup_steps and launch a real
    scan inside DiscoveryAgent — this is the mechanism that should NOT be
    used for interactive_scan projects any more (see below)."""

    def setUp(self):
        self.agent = DiscoveryAgent()
        self.request = {
            "url": "https://app.example/dashboard",
            "browser": "chromium",
            "headless": True,
            "project_name": "proj",
            "auth_storage_state": "/tmp/auth.json",
            "auth": _AUTH,
            "setup_steps": _SETUP_STEPS,
        }

    @patch("agents.comprehension.discovery.agent.save_dom_scan")
    @patch("agents.comprehension.discovery.agent.scan_dom")
    @patch("agents.comprehension.discovery.agent._load_dom_intents_raw", return_value=[])
    def test_headless_scan_receives_the_same_setup_steps_and_auth(
        self, _mock_intents, mock_scan_dom, mock_save
    ):
        mock_scan_dom.return_value = _dummy_headless_result()
        mock_save.return_value = {"dom_intents": "x", "dom_elements": "y"}

        self.request["interactive_scan"] = False
        self.agent._run_dom_scan(self.request, "proj")

        _, kwargs = mock_scan_dom.call_args
        self.assertEqual(kwargs["setup_steps"], _SETUP_STEPS)
        self.assertEqual(kwargs["storage_state_path"], "/tmp/auth.json")
        self.assertEqual(kwargs["auth_config"], _AUTH)


class DiscoveryAgentInteractiveReadsRecordingTests(unittest.TestCase):
    """interactive_scan projects no longer launch a live browser inside
    DiscoveryAgent (that would race a human-paced session against the timed
    discovery step — the original M04 bug). _run_dom_scan must instead read
    whatever `python main.py --record` already wrote to disk, doing no
    scanning of its own and never touching setup_steps/auth (those apply
    only at recording time — see test_record_cli_setup_parity.py)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        p = patch("agents.comprehension.discovery.agent._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)
        self.agent = DiscoveryAgent()

    def _comp_dir(self, safe, module_id=None):
        base = os.path.join(self.tmp_dir, safe, "test_comprehension")
        return os.path.join(base, "modules", module_id) if module_id else base

    def _write_recording(self, safe, module_id=None, element_count=1):
        comp_dir = self._comp_dir(safe, module_id)
        os.makedirs(comp_dir, exist_ok=True)
        with open(os.path.join(comp_dir, "dom_elements.json"), "w", encoding="utf-8") as f:
            json.dump({
                "url": "https://app.example/dashboard", "project": safe,
                "scan_mode": "interactive", "total_element_count": element_count,
                "elements": [{"locator_id": "LOC-0001"}] if element_count else [],
                "pages": [{"page_id": "PAGE-001", "elements": [{"locator_id": "LOC-0001"}] if element_count else []}],
            }, f)
        with open(os.path.join(comp_dir, "dom_intents.json"), "w", encoding="utf-8") as f:
            json.dump({"url": "https://x", "project": safe, "intents": [], "intent_count": 0}, f)
        return comp_dir

    def test_reads_module_scoped_recording_without_launching_a_scan(self):
        self._write_recording("proj", module_id="M04")

        with patch("agents.comprehension.discovery.agent.scan_dom") as mock_scan_dom:
            result = self.agent._run_dom_scan(
                {"url": "https://app.example/dashboard", "project_name": "proj",
                 "interactive_scan": True, "module_filter": "M04"},
                "proj",
            )

        mock_scan_dom.assert_not_called()
        self.assertEqual(result["dom_status"], "success")
        self.assertEqual(result["dom_pages_count"], 1)

    def test_missing_recording_fails_with_actionable_record_command(self):
        result = self.agent._run_dom_scan(
            {"url": "https://app.example/dashboard", "project_name": "proj",
             "interactive_scan": True, "module_filter": "M04"},
            "proj",
        )

        self.assertEqual(result["dom_status"], "failed")
        self.assertIn("--record", result["error"])
        self.assertIn("--module M04", result["error"])

    def test_falls_back_to_legacy_flat_layout_when_module_scoped_missing(self):
        # Simulates a project recorded before module-scoping existed (e.g. AmazonTest).
        self._write_recording("proj", module_id=None)

        result = self.agent._run_dom_scan(
            {"url": "https://app.example/dashboard", "project_name": "proj",
             "interactive_scan": True, "module_filter": "M04"},
            "proj",
        )

        self.assertEqual(result["dom_status"], "success")

    def test_never_forwards_setup_steps_or_auth_to_a_live_scan(self):
        # Even if setup_steps/auth are present in the request (as the
        # orchestrator always supplies them), the interactive branch must
        # not launch anything with them — recording already happened.
        self._write_recording("proj", module_id="M04")

        with patch("agents.comprehension.discovery.agent.scan_dom") as mock_scan_dom:
            self.agent._run_dom_scan(
                {
                    "url": "https://app.example/dashboard", "project_name": "proj",
                    "interactive_scan": True, "module_filter": "M04",
                    "setup_steps": _SETUP_STEPS, "auth": _AUTH,
                    "auth_storage_state": "/tmp/auth.json",
                },
                "proj",
            )

        mock_scan_dom.assert_not_called()


if __name__ == "__main__":
    unittest.main()
