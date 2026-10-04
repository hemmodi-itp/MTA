import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.discovery.interactive_dom_scan import scan_dom_interactive


class ScanDomInteractiveForwardsSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    @patch("tools.discovery.interactive_dom_scan.InteractiveScanner")
    def test_forwards_setup_steps_and_auth_to_scanner(self, mock_scanner_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan_interactive.return_value = {
            "elements": [], "element_count": 0, "pages": [],
            "total_element_count": 0, "_user_flows": [],
        }
        mock_scanner_cls.return_value = mock_scanner

        steps = [{"goto": "https://app.example/login"}]
        scan_dom_interactive(
            url="https://app.example/dashboard",
            browser="chromium",
            project_dir=self.tmp_dir,
            resume=False,
            storage_state_path="/tmp/auth.json",
            auth_config={"strategy": "live_login"},
            setup_steps=steps,
        )

        mock_scanner.scan_interactive.assert_called_once()
        _, kwargs = mock_scanner.scan_interactive.call_args
        self.assertEqual(kwargs["setup_steps"], steps)
        self.assertEqual(kwargs["storage_state_path"], "/tmp/auth.json")
        self.assertEqual(kwargs["auth_config"], {"strategy": "live_login"})

    @patch("tools.discovery.interactive_dom_scan.InteractiveScanner")
    def test_defaults_forward_as_none(self, mock_scanner_cls):
        mock_scanner = MagicMock()
        mock_scanner.scan_interactive.return_value = {
            "elements": [], "element_count": 0, "pages": [],
            "total_element_count": 0, "_user_flows": [],
        }
        mock_scanner_cls.return_value = mock_scanner

        scan_dom_interactive(url="https://app.example/dashboard", project_dir=self.tmp_dir)

        _, kwargs = mock_scanner.scan_interactive.call_args
        self.assertIsNone(kwargs["setup_steps"])
        self.assertIsNone(kwargs["storage_state_path"])
        self.assertIsNone(kwargs["auth_config"])


if __name__ == "__main__":
    unittest.main()
