import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.interactive_scanner import InteractiveScanner


class PageCloseHandlerTests(unittest.TestCase):
    """page 'close' fires the instant the tab/window closes — faster and
    more direct than waiting for the whole browser process to report
    'disconnected', which can lag on pages holding open WebSocket/service-
    worker connections (e.g. an authenticated app dashboard)."""

    def setUp(self):
        self.scanner = InteractiveScanner(browser_name="chromium")
        self.scanner.logger = MagicMock()
        self.scanner.browser = MagicMock()

    def test_setup_tracking_registers_page_close_handler(self):
        page = MagicMock()

        self.scanner._setup_tracking(page)

        close_registrations = [
            call for call in page.on.call_args_list if call.args[0] == "close"
        ]
        self.assertEqual(len(close_registrations), 1)
        self.assertEqual(close_registrations[0].args[1], self.scanner._handle_page_close)

    def test_handle_page_close_sets_stop_event(self):
        self.assertFalse(self.scanner._stop_event.is_set())

        self.scanner._handle_page_close()

        self.assertTrue(self.scanner._stop_event.is_set())

    def test_handle_page_close_flushes_checkpoint_as_complete_when_present(self):
        self.scanner._checkpoint_path = "/tmp/fake_checkpoint.json"
        self.scanner._flush_checkpoint = MagicMock()

        self.scanner._handle_page_close()

        self.scanner._flush_checkpoint.assert_called_once_with(status="complete")

    def test_handle_page_close_does_not_raise_without_checkpoint(self):
        self.scanner._checkpoint_path = ""
        self.scanner._handle_page_close()  # must not raise


if __name__ == "__main__":
    unittest.main()
