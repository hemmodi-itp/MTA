import logging
import os
import sys
from logging import Logger
from typing import Any, Dict


LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")

# Console format: clean, human-readable, no date noise
_CONSOLE_FORMAT = "%(asctime)s  %(name)-25s  %(message)s"
_CONSOLE_DATE = "%H:%M:%S"

# File format: full detail for post-run investigation
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


def ensure_log_dir(log_dir: str = LOG_DIR) -> None:
    os.makedirs(log_dir, exist_ok=True)


def resolve_log_dir(settings: Dict[str, Any]) -> str:
    """settings.logging.dir overrides the default <repo>/logs directory."""
    return (settings.get("logging", {}) or {}).get("dir") or LOG_DIR


def _safe_console_stream(stream):
    """Make console writes tolerate characters the terminal's codec can't encode.

    Windows consoles often use a legacy codepage (e.g. cp1252) instead of UTF-8,
    so log messages containing Unicode symbols would otherwise crash the process.
    """
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    return stream


def _console_handler(level: int) -> logging.StreamHandler:
    handler = logging.StreamHandler(_safe_console_stream(sys.stdout))
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt=_CONSOLE_DATE))
    return handler


def configure_logging(settings: Dict[str, Any]) -> None:
    log_dir = resolve_log_dir(settings)
    ensure_log_dir(log_dir)
    log_level = settings.get("logging", {}).get("level", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    file_formatter = logging.Formatter(_FILE_FORMAT)
    console = _console_handler(numeric_level)

    workflow_file = logging.FileHandler(
        os.path.join(log_dir, "workflow.log"), encoding="utf-8"
    )
    workflow_file.setFormatter(file_formatter)
    workflow_file.setLevel(numeric_level)

    agent_file = logging.FileHandler(
        os.path.join(log_dir, "agent.log"), encoding="utf-8"
    )
    agent_file.setFormatter(file_formatter)
    agent_file.setLevel(numeric_level)

    workflow_logger = logging.getLogger("workflow")
    workflow_logger.setLevel(numeric_level)
    workflow_logger.handlers = [workflow_file, console]
    workflow_logger.propagate = False

    agent_logger = logging.getLogger("agent")
    agent_logger.setLevel(numeric_level)
    agent_logger.handlers = [agent_file, console]
    agent_logger.propagate = False

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers = []


def get_logger(name: str) -> Logger:
    return logging.getLogger(name)
