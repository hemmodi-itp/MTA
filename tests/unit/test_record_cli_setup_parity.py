import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.discovery import record_cli

_SETUP_STEPS = [{"goto": "https://app.example/login"}, {"click": "#sso"}]
_AUTH = {"enabled": True, "strategy": "live_login"}


def _dummy_result():
    return {
        "elements": [], "element_count": 0, "pages": [],
        "total_element_count": 0, "_user_flows": [],
    }


class RecordCliSetupParityTests(unittest.TestCase):
    """`--record` (tools.discovery.record_cli.run_interactive_recording) must
    resolve module URL/setup_steps/auth the same way the normal pipeline
    does, and forward them to scan_dom_interactive exactly as
    DiscoveryAgent._run_dom_scan used to when it launched interactive scans
    directly. That call moved out of DiscoveryAgent (which now only reads
    pre-recorded artifacts from disk — see test_discovery_agent_setup_parity.py)
    and into this standalone CLI path as part of decoupling recording from
    the timed discovery step."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        for target in ("tools.discovery.record_cli._ASSETS_BASE", "tools.project_manifest._PROJECTS_DIR"):
            p = patch(target, self.tmp_dir)
            p.start()
            self.addCleanup(p.stop)

    def _write_manifest(self, project_name, modules=None, url=None, auth=None):
        project_dir = os.path.join(self.tmp_dir, project_name)
        os.makedirs(project_dir, exist_ok=True)
        project_block = {"interactive_scan": True}
        if url:
            project_block["url"] = url
        manifest = {"project": project_block}
        if modules:
            manifest["modules"] = modules
        if auth:
            manifest["auth"] = auth
        with open(os.path.join(project_dir, "project.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(manifest, f)

    @patch("tools.discovery.record_cli.save_dom_scan_interactive")
    @patch("tools.discovery.record_cli.scan_dom_interactive")
    def test_module_setup_steps_and_auth_forwarded(self, mock_scan, mock_save):
        mock_scan.return_value = _dummy_result()
        mock_save.return_value = {"dom_elements": "x", "dom_intents": "y"}
        self._write_manifest(
            "proj",
            modules=[{"id": "M04", "url": "https://app.example/dashboard", "setup": _SETUP_STEPS}],
            auth=_AUTH,
        )

        record_cli.run_interactive_recording("proj", "M04")

        _, kwargs = mock_scan.call_args
        self.assertEqual(kwargs["setup_steps"], _SETUP_STEPS)
        self.assertEqual(kwargs["auth_config"], _AUTH)
        self.assertEqual(kwargs["module_id"], "M04")
        self.assertEqual(kwargs["url"], "https://app.example/dashboard")

    @patch("tools.discovery.record_cli.save_dom_scan_interactive")
    @patch("tools.discovery.record_cli.scan_dom_interactive")
    def test_no_setup_steps_forwards_none_for_non_modular_project(self, mock_scan, mock_save):
        mock_scan.return_value = _dummy_result()
        mock_save.return_value = {"dom_elements": "x", "dom_intents": "y"}
        self._write_manifest("proj2", url="https://app.example/home")

        record_cli.run_interactive_recording("proj2")

        _, kwargs = mock_scan.call_args
        self.assertIsNone(kwargs["setup_steps"])
        self.assertIsNone(kwargs["module_id"])
        self.assertEqual(kwargs["url"], "https://app.example/home")

    def test_raises_when_interactive_scan_not_enabled(self):
        project_dir = os.path.join(self.tmp_dir, "proj3")
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "project.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump({"project": {"interactive_scan": False, "url": "https://x"}}, f)

        with self.assertRaises(ValueError):
            record_cli.run_interactive_recording("proj3")

    def test_raises_when_project_yaml_missing(self):
        with self.assertRaises(FileNotFoundError):
            record_cli.run_interactive_recording("does_not_exist")

    def test_raises_when_module_filter_does_not_match(self):
        self._write_manifest(
            "proj4",
            modules=[{"id": "M01", "url": "https://app.example/one"}],
        )
        with self.assertRaises(ValueError):
            record_cli.run_interactive_recording("proj4", "M99")


if __name__ == "__main__":
    unittest.main()
