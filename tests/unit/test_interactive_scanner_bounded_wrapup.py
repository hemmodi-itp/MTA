import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.interactive_scanner import InteractiveScanner


def _args():
    return ("https://example.com", None, None, None)


class RunWorkerBoundedTests(unittest.TestCase):
    """_run_worker_bounded must run launch/_run_sessions/close all on the
    same worker thread (Playwright's sync API is bound to a single OS
    thread), while still wrapping up quickly once stopping, even if a
    Playwright call is permanently blocked (the exact failure mode
    reported: close/disconnect events fire, but a Playwright call in
    flight when the browser died never returns)."""

    def setUp(self):
        self.scanner = InteractiveScanner(browser_name="chromium")
        self.scanner.logger = MagicMock()
        self.scanner._CLOSE_GRACE_S = 0.2
        self.fake_page = MagicMock()
        self.scanner.launch = MagicMock(return_value=self.fake_page)
        self.scanner._setup_tracking = MagicMock()
        self.scanner.close = MagicMock()

    def test_launch_and_run_sessions_happen_on_the_same_worker_thread(self):
        threads_seen = []

        def _record_thread(*_a, **_k):
            threads_seen.append(threading.current_thread())
            return self.fake_page

        def _record_run_sessions(page, url):
            threads_seen.append(threading.current_thread())

        self.scanner.launch = MagicMock(side_effect=_record_thread)
        self.scanner._run_sessions = _record_run_sessions

        self.scanner._run_worker_bounded(*_args())

        self.assertEqual(len(threads_seen), 2)
        self.assertIs(threads_seen[0], threads_seen[1])
        self.assertNotEqual(threads_seen[0], threading.current_thread())

    def test_returns_quickly_once_stop_event_set_even_if_run_sessions_never_returns(self):
        def wedged_run_sessions(page, url):
            threading.Event().wait()  # never returns

        self.scanner._run_sessions = wedged_run_sessions

        start = time.monotonic()

        def _close_shortly():
            time.sleep(0.05)
            self.scanner._stop_event.set()

        threading.Thread(target=_close_shortly, daemon=True).start()
        self.scanner._run_worker_bounded(*_args())
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 1.0, "must abandon the wedged thread within roughly the grace period")

    def test_waits_for_normal_completion_and_calls_close(self):
        calls = []
        self.scanner._run_sessions = lambda page, url: calls.append("ran")
        self.scanner.close = MagicMock(side_effect=lambda: calls.append("closed"))

        self.scanner._run_worker_bounded(*_args())

        self.assertEqual(calls, ["ran", "closed"])

    def test_exception_in_session_thread_is_caught_not_raised_and_close_still_runs(self):
        def raising_run_sessions(page, url):
            raise RuntimeError("boom")

        self.scanner._run_sessions = raising_run_sessions

        self.scanner._run_worker_bounded(*_args())  # must not raise

        self.scanner.close.assert_called_once()

    def test_wedged_close_after_normal_run_sessions_is_bounded_not_hung(self):
        self.scanner._run_sessions = lambda page, url: None
        self.scanner.close = lambda: threading.Event().wait()  # never returns

        start = time.monotonic()
        self.scanner._run_worker_bounded(*_args())
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 1.0, "a wedged close() must not hang scan_interactive() indefinitely")

    def test_exception_in_close_is_swallowed(self):
        self.scanner._run_sessions = lambda page, url: None
        self.scanner.close = MagicMock(side_effect=RuntimeError("boom"))

        self.scanner._run_worker_bounded(*_args())  # must not raise


if __name__ == "__main__":
    unittest.main()
