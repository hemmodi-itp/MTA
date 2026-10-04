import contextlib
import io
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools import startup


class DisplayStartupBannerTests(unittest.TestCase):
    def test_banner_contains_expected_content_without_rich(self):
        with mock.patch.object(startup, "_get_console", return_value=None):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                startup.display_startup_banner()
        output = buf.getvalue()

        self.assertIn(startup.APP_NAME, output)
        self.assertIn(startup.APP_VERSION, output)
        self.assertIn(startup.APP_TAGLINE, output)
        for _, label in startup.APP_FEATURES:
            self.assertIn(label, output)
        self.assertIn("Python Version", output)
        self.assertIn("Platform", output)
        self.assertIn("Execution Time", output)
        self.assertIn("Working Dir", output)

    def test_banner_prints_via_rich_console_when_available(self):
        from rich.console import Console as RichConsole

        buf = io.StringIO()
        real_console = RichConsole(file=buf, width=120, force_terminal=False)
        with mock.patch.object(startup, "_get_console", return_value=real_console):
            startup.display_startup_banner()

        output = buf.getvalue()
        self.assertIn(startup.APP_VERSION, output)
        # rendered letter-spaced ("A U T O N O M O U S ..."), not verbatim
        self.assertIn("AUTONOMOUS".replace("", " ").strip(), output)

    def test_banner_never_raises_when_console_lookup_fails(self):
        with mock.patch.object(startup, "_get_console", side_effect=RuntimeError("boom")):
            try:
                startup.display_startup_banner()
            except Exception as exc:  # noqa: BLE001 - explicitly asserting no raise
                self.fail(f"display_startup_banner raised unexpectedly: {exc}")

    def test_title_lines_are_uniform_width_and_non_empty(self):
        self.assertTrue(startup.BANNER_TITLE_LINES)
        widths = {len(line) for line in startup.BANNER_TITLE_LINES}
        self.assertEqual(len(widths), 1, "title rows must be equal width to stay aligned")


class DisplayPlatformReadyTests(unittest.TestCase):
    DETAILS = {"Provider": "aws", "Workflow": "full_workflow", "Run ID": "ab12cd34"}
    CHECKLIST = ["Loading Configuration", "Initializing Logger", "All Systems Ready"]

    def test_platform_ready_contains_details_and_checklist_without_rich(self):
        with mock.patch.object(startup, "_get_console", return_value=None):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                startup.display_platform_ready(self.DETAILS, self.CHECKLIST)
        output = buf.getvalue()

        for label, value in self.DETAILS.items():
            self.assertIn(label, output)
            self.assertIn(value, output)
        for item in self.CHECKLIST:
            self.assertIn(item, output)
        self.assertIn(startup.APP_READY_HEADLINE, output)

    def test_platform_ready_prints_via_rich_console_when_available(self):
        from rich.console import Console as RichConsole

        buf = io.StringIO()
        real_console = RichConsole(file=buf, width=120, force_terminal=False)
        with mock.patch.object(startup, "_get_console", return_value=real_console):
            startup.display_platform_ready(self.DETAILS, self.CHECKLIST)

        output = buf.getvalue()
        self.assertIn(startup.APP_READY_HEADLINE, output)
        for item in self.CHECKLIST:
            self.assertIn(item, output)

    def test_never_raises_when_console_lookup_fails(self):
        with mock.patch.object(startup, "_get_console", side_effect=RuntimeError("boom")):
            try:
                startup.display_platform_ready(self.DETAILS, self.CHECKLIST)
            except Exception as exc:  # noqa: BLE001 - explicitly asserting no raise
                self.fail(f"display_platform_ready raised unexpectedly: {exc}")

    def test_long_value_does_not_raise_and_is_still_present(self):
        long_path = "C:\\Projects\\agentic-qa-platform\\some\\very\\deep\\workspace\\path"
        details = {**self.DETAILS, "Workspace": long_path}
        with mock.patch.object(startup, "_get_console", return_value=None):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                startup.display_platform_ready(details, self.CHECKLIST)
        self.assertIn(long_path, buf.getvalue())


class SplitFactsTests(unittest.TestCase):
    def test_short_values_stay_together(self):
        facts = [("A", "1"), ("B", "2")]
        short, long = startup._split_facts(facts)
        self.assertEqual(short, facts)
        self.assertEqual(long, [])

    def test_long_value_is_separated(self):
        long_value = "x" * (startup._LONG_VALUE_THRESHOLD + 1)
        facts = [("Short", "ok"), ("Long", long_value)]
        short, long = startup._split_facts(facts)
        self.assertEqual(short, [("Short", "ok")])
        self.assertEqual(long, [("Long", long_value)])


class StartupStatusTests(unittest.TestCase):
    def _capture(self, message, status="ok"):
        with mock.patch.object(startup, "_get_console", return_value=None):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                startup.startup_status(message, status=status)
        return buf.getvalue()

    def test_ok_status_uses_checkmark(self):
        output = self._capture("Loading Configuration")
        self.assertIn("[✓] Loading Configuration", output)

    def test_warn_status_uses_warning_symbol(self):
        output = self._capture("Disk space low", status="warn")
        self.assertIn("[!] Disk space low", output)

    def test_fail_status_uses_cross_symbol(self):
        output = self._capture("Provider unreachable", status="fail")
        self.assertIn("[✗] Provider unreachable", output)

    def test_unknown_status_falls_back_to_ok(self):
        output = self._capture("Something", status="not-a-real-status")
        self.assertIn("[✓] Something", output)

    def test_status_never_raises_when_console_lookup_fails(self):
        with mock.patch.object(startup, "_get_console", side_effect=RuntimeError("boom")):
            try:
                startup.startup_status("Loading Configuration")
            except Exception as exc:  # noqa: BLE001 - explicitly asserting no raise
                self.fail(f"startup_status raised unexpectedly: {exc}")


class ConfigureStdoutEncodingTests(unittest.TestCase):
    def _cp1252_stream(self):
        buffer = io.BytesIO()
        return buffer, io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")

    def test_does_not_raise_on_strict_legacy_codepage_stream(self):
        _, stream = self._cp1252_stream()
        with mock.patch.object(sys, "stdout", stream), mock.patch.object(sys, "stderr", stream):
            startup._configure_stdout_encoding()
            stream.write("Startup → banner")
            stream.flush()

    def test_unicode_write_crashes_without_reconfigure(self):
        _, stream = self._cp1252_stream()
        with self.assertRaises(UnicodeEncodeError):
            stream.write("Startup → banner")

    def test_handles_streams_without_reconfigure(self):
        class NoReconfigure:
            pass

        with mock.patch.object(sys, "stdout", NoReconfigure()), mock.patch.object(
            sys, "stderr", NoReconfigure()
        ):
            startup._configure_stdout_encoding()  # must not raise


if __name__ == "__main__":
    unittest.main()
