import os
import sys
import time
import unittest
import unittest.mock
import urllib.parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.playwright_scanner import PlaywrightScanner, _same_page

_SETUP_DELAY_S = 3


class SamePageTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(_same_page("https://x.com/a/b", "https://x.com/a/b"))

    def test_trailing_slash_ignored(self):
        self.assertTrue(_same_page("https://x.com/a/b/", "https://x.com/a/b"))

    def test_query_string_and_fragment_ignored(self):
        self.assertTrue(_same_page("https://x.com/a/b?x=1#foo", "https://x.com/a/b"))

    def test_different_path_is_not_a_match(self):
        self.assertFalse(_same_page("https://x.com/a/c", "https://x.com/a/b"))

    def test_different_host_is_not_a_match(self):
        self.assertFalse(_same_page("https://y.com/a/b", "https://x.com/a/b"))

    def test_malformed_url_does_not_raise(self):
        self.assertFalse(_same_page("not a url", "https://x.com/a/b"))


class PlaywrightScannerTests(unittest.TestCase):
    def test_scan_page_data_url(self):
        html = (
            "<html><body>"
            "<input id=origin name=origin placeholder='From' value='' />"
            "<input id=destination name=destination placeholder='To' value='' />"
            "<button type='submit'>Search</button>"
            "</body></html>"
        )
        url = f"data:text/html,{urllib.parse.quote(html)}"
        runner = PlaywrightScanner(headless=True)
        result = runner.scan_page(url)
        self.assertEqual(result["url"], url)
        self.assertTrue(any(element["tag"] == "input" for element in result["elements"]))
        self.assertTrue(any(element["tag"] == "button" for element in result["elements"]))

    def test_setup_steps_wait_action(self):
        """wait: N action calls page.wait_for_timeout(N) without error."""
        scanner = PlaywrightScanner(headless=True)
        mock_page = unittest.mock.MagicMock()
        steps = [{"wait": 500}]
        scanner._execute_setup_steps(mock_page, steps)
        mock_page.wait_for_timeout.assert_called_once_with(500)

    def test_setup_steps_unknown_action_is_skipped(self):
        """Unknown actions log a warning and do not raise."""
        scanner = PlaywrightScanner(headless=True)
        mock_page = unittest.mock.MagicMock()
        steps = [{"teleport": "somewhere"}]
        scanner._execute_setup_steps(mock_page, steps)  # must not raise

    def test_setup_steps_non_dict_step_is_skipped(self):
        """Non-dict steps (e.g. plain strings) log a warning and do not raise."""
        scanner = PlaywrightScanner(headless=True)
        mock_page = unittest.mock.MagicMock()
        scanner._execute_setup_steps(mock_page, ["click something"])  # must not raise

    def test_setup_steps_data_test_selector_fill(self):
        """fill with data-test selector calls page.locator(...).fill(value)."""
        scanner = PlaywrightScanner(headless=True)
        mock_page = unittest.mock.MagicMock()
        mock_locator = unittest.mock.MagicMock()
        mock_page.locator.return_value = mock_locator
        steps = [{"fill": {"selector": "[data-test='username']", "value": "standard_user"}}]
        scanner._execute_setup_steps(mock_page, steps)
        mock_page.locator.assert_called_once_with("[data-test='username']")
        mock_locator.fill.assert_called_once_with("standard_user")

    def test_setup_steps_fill_resolves_value_env_from_environment(self):
        """fill with value_env reads the named env var, not a literal — the
        actual secret must never live in project.yaml or generated code."""
        scanner = PlaywrightScanner(headless=True)
        mock_page = unittest.mock.MagicMock()
        mock_locator = unittest.mock.MagicMock()
        mock_page.locator.return_value = mock_locator
        steps = [{"fill": {"selector": "#username", "value_env": "TEST_SETUP_STEP_USERNAME"}}]
        with unittest.mock.patch.dict(os.environ, {"TEST_SETUP_STEP_USERNAME": "resolved_value"}):
            scanner._execute_setup_steps(mock_page, steps)
        mock_locator.fill.assert_called_once_with("resolved_value")

    def test_setup_steps_fill_value_env_missing_fills_empty_string(self):
        """An unset value_env logs a warning and fills empty string, rather
        than raising or silently using some other fallback."""
        scanner = PlaywrightScanner(headless=True)
        mock_page = unittest.mock.MagicMock()
        mock_locator = unittest.mock.MagicMock()
        mock_page.locator.return_value = mock_locator
        steps = [{"fill": {"selector": "#username", "value_env": "TEST_SETUP_STEP_DOES_NOT_EXIST"}}]
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_SETUP_STEP_DOES_NOT_EXIST", None)
            scanner._execute_setup_steps(mock_page, steps)
        mock_locator.fill.assert_called_once_with("")

    def test_scan_page_with_setup_steps_runs_login_sequence(self):
        """scan_page calls _execute_setup_steps before navigating to the target URL."""
        html = "<html><body><h1 id='inv'>Inventory</h1></body></html>"
        url = f"data:text/html,{urllib.parse.quote(html)}"
        scanner = PlaywrightScanner(headless=True)
        setup_calls = []

        original_execute = scanner._execute_setup_steps

        def _capture_steps(page, steps):
            setup_calls.extend(steps)
            return original_execute(page, steps)

        scanner._execute_setup_steps = _capture_steps
        setup_steps = [
            {"goto": "data:text/html,<html></html>"},
            {"wait": 100},
        ]
        result = scanner.scan_page(url, setup_steps=setup_steps)
        self.assertEqual(setup_calls, setup_steps)
        self.assertIn("elements", result)

    def test_scan_budget_excludes_setup_step_duration(self):
        """The 30s scan budget must start after setup steps (e.g. a multi-step
        login) finish, not before — a slow login sequence must not eat into
        the time available to actually scan the page. Verified by checking the
        elapsed time in the first DOM-readiness log line stays well below a
        real delay inside setup — under the old bug it would include the delay.
        (The log line rounds to whole seconds and navigation itself can take
        ~1s on a loaded machine, so the delay is made large enough to tell the
        two apart instead of asserting an exact 0.)"""
        html = "<html><body></body></html>"
        url = f"data:text/html,{urllib.parse.quote(html)}"
        runner = PlaywrightScanner(headless=True)
        original_execute = runner._execute_setup_steps

        def _slow_setup(page, steps):
            time.sleep(_SETUP_DELAY_S)
            original_execute(page, steps)

        runner._execute_setup_steps = _slow_setup

        with self.assertLogs(runner.logger, level="INFO") as captured:
            runner.scan_page(url, setup_steps=[{"wait": 1}])

        dom_lines = [line for line in captured.output if "DOM [" in line and "readyState=" in line]
        self.assertTrue(dom_lines, "expected at least one DOM readiness log line")
        first_elapsed = int(dom_lines[0].split("DOM [")[1].split("s/")[0])
        self.assertLess(
            first_elapsed, _SETUP_DELAY_S,
            "scan budget clock must start after setup steps, not before "
            f"(elapsed >= {_SETUP_DELAY_S}s means the setup delay leaked into the budget)",
        )

    def test_scan_page_collects_more_than_the_old_100_element_cap(self):
        """The old _MAX_ELEMENTS=100 truncation is gone — a page with more
        than 100 matching elements (e.g. a dashboard with many cards) must
        have every one of them collected, including the links, which used
        to be scanned last and lose out to the cap first."""
        buttons = "".join(f"<button id='b{i}'>Button {i}</button>" for i in range(110))
        links = "".join(f"<a id='l{i}' href='/page{i}'>Link {i}</a>" for i in range(5))
        html = f"<html><body>{buttons}{links}</body></html>"
        url = f"data:text/html,{urllib.parse.quote(html)}"
        runner = PlaywrightScanner(headless=True)

        result = runner.scan_page(url)

        self.assertEqual(result["element_count"], 115)
        link_count = sum(1 for e in result["elements"] if e["tag"] == "a")
        self.assertEqual(link_count, 5, "links must not be truncated by an element-count cap")


if __name__ == "__main__":
    unittest.main()
