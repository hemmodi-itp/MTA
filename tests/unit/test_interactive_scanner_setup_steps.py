import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.interactive_scanner import InteractiveScanner


def _silence_platform_bits(scanner):
    """Interactive scanning does real signal-handler registration and browser
    teardown — irrelevant to the setup_steps wiring under test, so stub them."""
    scanner._register_signals = MagicMock()
    scanner._restore_signals = MagicMock()
    scanner._cancel_timers = MagicMock()
    scanner.close = MagicMock()
    scanner._setup_tracking = MagicMock()
    scanner._build_result = MagicMock(return_value={"total_element_count": 0, "pages": [], "_user_flows": []})


class ScanInteractiveSetupStepsTests(unittest.TestCase):
    def setUp(self):
        self.scanner = InteractiveScanner(browser_name="chromium")
        _silence_platform_bits(self.scanner)
        self.fake_page = MagicMock()
        self.scanner.launch = MagicMock(return_value=self.fake_page)
        self.scanner._run_sessions = MagicMock()
        self.scanner._execute_setup_steps = MagicMock()

    def test_setup_steps_run_before_sessions_start(self):
        calls = []
        self.scanner._execute_setup_steps.side_effect = lambda page, steps: calls.append("setup")
        self.scanner._run_sessions.side_effect = lambda page, url: calls.append("sessions")

        steps = [{"goto": "https://app.example/login"}, {"click": "#sso"}]
        self.scanner.scan_interactive(url="https://app.example/dashboard", setup_steps=steps)

        self.scanner._execute_setup_steps.assert_called_once_with(self.fake_page, steps)
        self.assertEqual(calls, ["setup", "sessions"])

    def test_no_setup_steps_skips_execute_setup_steps(self):
        self.scanner.scan_interactive(url="https://app.example/dashboard", setup_steps=None)

        self.scanner._execute_setup_steps.assert_not_called()
        self.scanner._run_sessions.assert_called_once()

    def test_launch_receives_storage_state_and_auth_config(self):
        auth_cfg = {"strategy": "live_login"}
        self.scanner.scan_interactive(
            url="https://app.example/dashboard",
            storage_state_path="/tmp/auth.json",
            auth_config=auth_cfg,
        )

        self.scanner.launch.assert_called_once_with(
            storage_state_path="/tmp/auth.json", auth_config=auth_cfg
        )


if __name__ == "__main__":
    unittest.main()
