import os
import sys
import threading
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.interactive_scanner import InteractiveScanner


class RegisterSignalsWarningTests(unittest.TestCase):
    """signal.signal() only works in the main thread — when a background
    thread runs the interactive scan (the normal case via DiscoveryAgent),
    registration must fail loudly (a warning), not silently, since it means
    Ctrl+C can't gracefully stop this session."""

    def test_logs_warning_when_registration_fails_off_main_thread(self):
        scanner = InteractiveScanner(browser_name="chromium")
        scanner.logger = MagicMock()

        result_holder = {}

        def _call_from_worker_thread():
            try:
                scanner._register_signals()
            except Exception as exc:
                result_holder["error"] = exc

        t = threading.Thread(target=_call_from_worker_thread)
        t.start()
        t.join()

        self.assertNotIn("error", result_holder, "must not raise, only warn")
        scanner.logger.warning.assert_called_once()
        warning_text = scanner.logger.warning.call_args[0][0]
        self.assertIn("signal handlers", warning_text.lower())

    def test_succeeds_silently_on_main_thread(self):
        scanner = InteractiveScanner(browser_name="chromium")
        scanner.logger = MagicMock()

        scanner._register_signals()
        scanner._restore_signals()

        scanner.logger.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
