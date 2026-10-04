import io
import logging
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.file_manager import load_yaml_file
from tools.logger_config import _safe_console_stream, configure_logging, get_logger


class LoggingTests(unittest.TestCase):
    def test_logging_writes_files(self):
        with tempfile.TemporaryDirectory() as log_dir:
            settings = {"logging": {"level": "INFO", "dir": log_dir}}
            configure_logging(settings)
            try:
                logger = get_logger("agent.test")
                logger.info("Test logging")
                for name in ("workflow", "agent"):
                    for handler in logging.getLogger(name).handlers:
                        handler.flush()

                workflow_log = os.path.join(log_dir, "workflow.log")
                agent_log = os.path.join(log_dir, "agent.log")

                self.assertTrue(os.path.exists(workflow_log))
                self.assertTrue(os.path.exists(agent_log))
                self.assertGreater(os.path.getsize(agent_log), 0)
            finally:
                # Release the file handles so the temp dir can be removed (Windows).
                for name in ("workflow", "agent"):
                    log = logging.getLogger(name)
                    for handler in log.handlers:
                        handler.close()
                    log.handlers = []

    def test_default_log_dir_is_repo_logs(self):
        from tools.logger_config import LOG_DIR, resolve_log_dir
        self.assertEqual(resolve_log_dir({"logging": {"level": "INFO"}}), LOG_DIR)
        self.assertEqual(
            os.path.normpath(LOG_DIR),
            os.path.normpath(os.path.join(ROOT, "logs")),
        )


class SafeConsoleStreamTests(unittest.TestCase):
    def _cp1252_stream(self):
        buffer = io.BytesIO()
        return buffer, io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")

    def test_unicode_write_crashes_without_fix(self):
        _, stream = self._cp1252_stream()
        with self.assertRaises(UnicodeEncodeError):
            stream.write("Module override → done")

    def test_safe_console_stream_does_not_crash_on_unicode(self):
        buffer, stream = self._cp1252_stream()
        safe_stream = _safe_console_stream(stream)

        safe_stream.write("Module override → done")
        safe_stream.flush()

        written = buffer.getvalue().decode("cp1252")
        self.assertIn("\\u2192", written)

    def test_console_handler_emits_unicode_log_record_without_raising(self):
        buffer, stream = self._cp1252_stream()
        safe_stream = _safe_console_stream(stream)

        handler = logging.StreamHandler(safe_stream)
        record = logging.LogRecord(
            name="workflow",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="Module 'M02' overrides URL → https://example.com",
            args=(),
            exc_info=None,
        )

        handler.emit(record)
        handler.flush()

        self.assertIn(b"\\u2192", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
