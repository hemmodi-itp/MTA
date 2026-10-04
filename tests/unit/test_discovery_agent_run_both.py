import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.comprehension.discovery.agent import DiscoveryAgent


class RunBothUsesDaemonThreadsTests(unittest.TestCase):
    """Regression guard: _run_both must use plain daemon threads, not
    ThreadPoolExecutor — a wedged DOM scan (Playwright hang after the
    browser closes) must never block process exit via the global
    concurrent.futures.thread atexit hook."""

    def setUp(self):
        self.agent = DiscoveryAgent()
        self.agent._run_comprehension = MagicMock(return_value={"comprehension_status": "success"})
        self.agent._run_dom_scan = MagicMock(return_value={"dom_status": "success", "dom_intents_raw": []})
        self.agent._save_intents_yaml = MagicMock(return_value="fake/intents.yaml")

    @patch("agents.comprehension.discovery.agent.threading.Thread")
    def test_both_worker_threads_are_daemon(self, mock_thread_cls):
        # Each Thread(...) call must return something .start()/.join()-able;
        # is_alive=False so the (unrelated) timeout-abandon path isn't
        # spuriously triggered by a bare MagicMock being truthy.
        mock_thread_cls.return_value = MagicMock(is_alive=MagicMock(return_value=False))

        self.agent._run_both({}, {}, "proj")

        self.assertEqual(mock_thread_cls.call_count, 2)
        for _, kwargs in mock_thread_cls.call_args_list:
            self.assertTrue(kwargs.get("daemon"), "worker thread must be created with daemon=True")

    def test_successful_run_merges_comp_and_scan_results(self):
        result = self.agent._run_both({}, {}, "proj")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["comprehension_status"], "success")
        self.assertEqual(result["dom_status"], "success")
        self.assertEqual(result["intents_path"], "fake/intents.yaml")

    def test_exception_in_one_thread_marks_status_partial_not_raised(self):
        self.agent._run_dom_scan.side_effect = RuntimeError("boom")

        result = self.agent._run_both({}, {}, "proj")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["comprehension_status"], "success")

    def test_runs_concurrently_not_sequentially(self):
        # Two real threads with a small sleep each — if they ran sequentially
        # this would take ~2x as long as running concurrently.
        def slow_comp(*_a, **_kw):
            time.sleep(0.2)
            return {"comprehension_status": "success"}

        def slow_scan(*_a, **_kw):
            time.sleep(0.2)
            return {"dom_status": "success", "dom_intents_raw": []}

        self.agent._run_comprehension = slow_comp
        self.agent._run_dom_scan = slow_scan

        start = time.monotonic()
        self.agent._run_both({}, {}, "proj")
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 0.35, "expected concurrent execution, not ~0.4s sequential")


class RunBothTimeoutTests(unittest.TestCase):
    """A wedged worker (e.g. an interactive scan whose Playwright session
    never returns after the browser closes) must be abandoned after a
    bounded wait instead of hanging _run_both — and therefore the whole
    discovery step — forever."""

    def setUp(self):
        self.agent = DiscoveryAgent()
        self.agent._run_comprehension = MagicMock(return_value={"comprehension_status": "success"})
        self.agent._save_intents_yaml = MagicMock(return_value="fake/intents.yaml")

    def test_wedged_scan_is_abandoned_after_configured_timeout(self):
        never_set = threading.Event()

        def wedged_scan(*_a, **_kw):
            never_set.wait()  # never set — simulates a permanently hung call
            return {"dom_status": "success"}  # unreachable in this test

        self.agent._run_dom_scan = wedged_scan

        start = time.monotonic()
        result = self.agent._run_both({"discovery_timeout_s": 0.2}, {}, "proj")
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 2.0, "must not block beyond roughly the configured timeout")
        self.assertEqual(result["dom_status"], "failed")
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["status"], "partial")  # comprehension still succeeded

    def test_default_timeout_constant_is_positive_and_reasonable(self):
        self.assertGreater(DiscoveryAgent._DISCOVERY_PARALLEL_TIMEOUT_S, 10)
        self.assertLessEqual(DiscoveryAgent._DISCOVERY_PARALLEL_TIMEOUT_S, 300)

    @patch("agents.comprehension.discovery.agent.threading.Thread")
    def test_no_discovery_timeout_s_joins_with_no_timeout(self, mock_thread_cls):
        """No discovery_timeout_s in the request (the common case — no per-run
        override, no project.yaml project.discovery_timeout_s) must wait
        indefinitely for both threads, not silently apply the old 60s default."""
        mock_thread_cls.return_value = MagicMock(is_alive=MagicMock(return_value=False))

        self.agent._run_both({}, {}, "proj")

        for call in mock_thread_cls.return_value.join.call_args_list:
            self.assertIsNone(
                call.kwargs.get("timeout"),
                "join() must be called with timeout=None when discovery_timeout_s is absent",
            )

    @patch("agents.comprehension.discovery.agent.threading.Thread")
    def test_explicit_discovery_timeout_s_still_bounds_the_join(self, mock_thread_cls):
        mock_thread_cls.return_value = MagicMock(is_alive=MagicMock(return_value=False))

        self.agent._run_both({"discovery_timeout_s": 600}, {}, "proj")

        for call in mock_thread_cls.return_value.join.call_args_list:
            timeout = call.kwargs.get("timeout")
            self.assertIsNotNone(timeout)
            self.assertLessEqual(timeout, 600)


if __name__ == "__main__":
    unittest.main()
