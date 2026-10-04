"""Enterprise-style startup banner for the QA Agentic Platform.

This module renders a decorative green dashboard the very first time the
application starts, before configuration loading, logging, dependency
injection, agent registration, or workflow execution. A second panel,
:func:`display_platform_ready`, is meant to be called once real startup
facts (settings, registry, run id, ...) are actually known.

Design constraints (do not violate when editing):
  * standard library only, with an *optional* dependency on ``rich`` for
    richer panel/table rendering. If ``rich`` is missing, everything
    degrades to plain ANSI escape sequences.
  * no imports from ``agents``, ``workflows``, or any provider package —
    this module must be safely importable before any of those subsystems
    exist. Callers pass in whatever real facts they want displayed;
    this module never invents data it can't independently verify.
  * nothing in here may raise. A broken terminal or missing dependency must
    never prevent the platform from starting.
  * icons are plain monochrome unicode symbols, never color emoji — emoji
    render in fixed colors that can't be restyled, which would break the
    all-green theme.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from rich import box as rich_box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    _RICH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when rich isn't installed
    rich_box = Align = Console = Group = Panel = Table = Text = None  # type: ignore[assignment]
    _RICH_AVAILABLE = False

APP_NAME = "QA Agentic Platform"
APP_VERSION = "1.1.2"
APP_TAGLINE = "AUTONOMOUS QUALITY ENGINEERING PLATFORM"
APP_READY_HEADLINE = "PLATFORM READY"
APP_READY_TAGLINE = "Let's build quality, together."
APP_FOOTER_TAGLINE = "BUILT WITH AGENTS  ·  POWERED BY INTELLIGENCE"

# (icon, label) pairs for the feature row. Icons are plain unicode symbols
# (Geometric Shapes / Dingbats blocks) so they inherit the green theme and
# stay aligned across terminals — never color emoji, see module docstring.
APP_FEATURES: List[Tuple[str, str]] = [
    ("◆", "AI AGENTS"),
    ("▣", "WORKFLOWS"),
    ("▶", "PLAYWRIGHT"),
    ("◈", "MCP"),
    ("▤", "REPORTS"),
    ("✚", "HEALING"),
    ("◉", "OBSERVABILITY"),
]

_STAR_ROW = "✦  ✧  ★  ✧  ✦"

_SEPARATOR_WIDTH = 64
_SEPARATOR = "━" * _SEPARATOR_WIDTH

# Wide enough to fit the block-letter title without Rich reflowing it as
# wrapped prose. If the real terminal is wider, that width wins instead.
_MIN_PANEL_WIDTH = 90

# Values longer than this (e.g. filesystem paths) get their own full-width
# line instead of a grid cell, so they can't overflow and break row layout.
_LONG_VALUE_THRESHOLD = 26

_ANSI_BRIGHT_GREEN = "\033[1;92m"
_ANSI_GREEN = "\033[92m"
_ANSI_YELLOW = "\033[93m"
_ANSI_RED = "\033[91m"
_ANSI_RESET = "\033[0m"

# 6-row block-letter font, restricted to the letters "AGENTIC QA" needs.
_LETTERS: Dict[str, List[str]] = {
    "A": [
        " █████╗ ",
        "██╔══██╗",
        "███████║",
        "██╔══██║",
        "██║  ██║",
        "╚═╝  ╚═╝",
    ],
    "G": [
        " ██████╗ ",
        "██╔════╝ ",
        "██║  ███╗",
        "██║   ██║",
        "╚██████╔╝",
        " ╚═════╝ ",
    ],
    "E": [
        "███████╗",
        "██╔════╝",
        "█████╗  ",
        "██╔══╝  ",
        "███████╗",
        "╚══════╝",
    ],
    "N": [
        "███╗   ██╗",
        "████╗  ██║",
        "██╔██╗ ██║",
        "██║╚██╗██║",
        "██║ ╚████║",
        "╚═╝  ╚═══╝",
    ],
    "T": [
        "████████╗",
        "╚══██╔══╝",
        "   ██║   ",
        "   ██║   ",
        "   ██║   ",
        "   ╚═╝   ",
    ],
    "I": [
        "██╗",
        "██║",
        "██║",
        "██║",
        "██║",
        "╚═╝",
    ],
    "C": [
        " ██████╗",
        "██╔════╝",
        "██║     ",
        "██║     ",
        "╚██████╗",
        " ╚═════╝",
    ],
    "Q": [
        " ██████╗ ",
        "██╔═══██╗",
        "██║   ██║",
        "██║▄▄ ██║",
        "╚██████╔╝",
        " ╚══▀▀═╝ ",
    ],
    " ": ["  ", "  ", "  ", "  ", "  ", "  "],
}


def _render_word(word: str) -> List[str]:
    """Render a word into 6 lines of block-letter ASCII art."""
    return ["".join(_LETTERS[ch][row] for ch in word) for row in range(6)]


BANNER_TITLE_LINES: List[str] = _render_word("AGENTIC QA")

_console: Optional["Console"] = None


def _configure_stdout_encoding() -> None:
    """Make stdout render the banner's box-drawing/Unicode chars correctly.

    Windows terminals are frequently stuck on a legacy codepage (cp1252)
    that cannot encode the banner's box-drawing characters. Prefer
    re-encoding as UTF-8, which modern terminals (Windows Terminal, VS
    Code, PowerShell 7) display correctly. If that fails, fall back to
    ``errors="replace"`` on the existing encoding so unencodable characters
    degrade to '?' instead of raising ``UnicodeEncodeError`` and killing
    startup.
    """
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            try:
                stream.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass


def _enable_windows_ansi() -> None:
    """Turn on ANSI/VT100 escape processing in legacy Windows consoles."""
    if platform.system() == "Windows":
        try:
            os.system("")
        except OSError:
            pass


def _get_console() -> Optional["Console"]:
    """Return a lazily-created, cached Rich console, or None if unavailable."""
    global _console
    if not _RICH_AVAILABLE:
        return None
    if _console is None:
        try:
            terminal_width = shutil.get_terminal_size(fallback=(80, 24)).columns
            _console = Console(width=max(terminal_width, _MIN_PANEL_WIDTH))
        except Exception:  # pragma: no cover - defensive, Rich should not fail here
            _console = None
    return _console


def _print_green(text: str, *, bold: bool = False) -> None:
    """Print a line of text in bright green, via Rich if available."""
    try:
        console = _get_console()
    except Exception:  # pragma: no cover - defensive
        console = None
    if console is not None:
        try:
            style = "bold bright_green" if bold else "bright_green"
            console.print(text, style=style)
            return
        except Exception:  # pragma: no cover - fall through to ANSI
            pass
    color = _ANSI_BRIGHT_GREEN if bold else _ANSI_GREEN
    try:
        print(f"{color}{text}{_ANSI_RESET}")
    except Exception:  # pragma: no cover - last-resort plain print
        _print_plain(text)


def _print_plain(text: str = "") -> None:
    """Print an uncolored line, tolerating any console encoding issues."""
    try:
        print(text)
    except Exception:  # pragma: no cover - defensive
        pass


def _panel(renderable, *, console: "Console") -> None:
    """Print a renderable wrapped in a rounded, bright-green panel."""
    console.print(
        Panel(
            renderable,
            box=rich_box.ROUNDED,
            border_style="bright_green",
            padding=(1, 3),
            expand=False,
        )
    )


def _feature_table_rich() -> "Table":
    table = Table.grid(padding=(0, 2))
    for _ in APP_FEATURES:
        table.add_column(justify="center")
    table.add_row(*(Text(icon, style="bold bright_green", justify="center") for icon, _ in APP_FEATURES))
    table.add_row(*(Text(label, style="green", justify="center") for _, label in APP_FEATURES))
    return table


def _split_facts(
    facts: Sequence[Tuple[str, str]]
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Split facts into short ones (fit a grid cell) and long ones (own line).

    Long values — filesystem paths chief among them — can't be predicted to
    fit any fixed column width, so they get a dedicated full-width line
    instead of risking a wrapped, misaligned grid cell.
    """
    short_facts = [(label, value) for label, value in facts if len(value) <= _LONG_VALUE_THRESHOLD]
    long_facts = [(label, value) for label, value in facts if len(value) > _LONG_VALUE_THRESHOLD]
    return short_facts, long_facts


def _facts_grid_rich(facts: Sequence[Tuple[str, str]], columns: int) -> "Table":
    table = Table.grid(padding=(0, 3))
    for _ in range(columns):
        table.add_column(justify="left")
    for row_start in range(0, len(facts), columns):
        row = facts[row_start:row_start + columns]
        cells = []
        for label, value in row:
            cell = Text(no_wrap=True, overflow="crop")
            cell.append(f"{label:<10}", style="dim green")
            cell.append(f": {value}", style="bold bright_green")
            cells.append(cell)
        while len(cells) < columns:
            cells.append(Text(""))
        table.add_row(*cells)
    return table


def _long_facts_lines_rich(facts: Sequence[Tuple[str, str]]) -> List["Text"]:
    lines = []
    for label, value in facts:
        line = Text(no_wrap=True, overflow="crop")
        line.append(f"{label:<10}", style="dim green")
        line.append(f": {value}", style="bold bright_green")
        lines.append(line)
    return lines


def display_startup_banner() -> None:
    """Render the QA Agentic Platform startup banner.

    Must be the very first thing the application does: before config
    loading, logging setup, dependency injection, agent registration, or
    workflow execution. Only shows facts knowable at that point (version,
    interpreter, platform, working directory). Never raises — any failure
    degrades to a simpler plain-text banner instead of interrupting startup.
    """
    _configure_stdout_encoding()
    _enable_windows_ansi()

    try:
        console = _get_console()
    except Exception:  # pragma: no cover - defensive
        console = None

    if console is not None:
        try:
            _display_startup_banner_rich(console)
            return
        except Exception:  # pragma: no cover - fall through to ANSI
            pass

    _display_startup_banner_ansi()


def _display_startup_banner_rich(console: "Console") -> None:
    facts = [
        ("VERSION", APP_VERSION),
        ("PYTHON", platform.python_version()),
        ("PLATFORM", platform.system()),
        ("STARTED AT", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("WORKSPACE", os.getcwd()),
    ]
    short_facts, long_facts = _split_facts(facts)
    title = Text("\n".join(BANNER_TITLE_LINES), style="bold bright_green", no_wrap=True, overflow="crop")
    body = Group(
        Align.center(Text(_STAR_ROW, style="dim green")),
        Align.center(title),
        Align.center(Text(" ".join(APP_TAGLINE), style="green")),
        Text(""),
        Align.center(_feature_table_rich()),
        Text(""),
        Align.center(_facts_grid_rich(short_facts, columns=2)),
        *(Align.center(line) for line in _long_facts_lines_rich(long_facts)),
    )
    _panel(body, console=console)


def _display_startup_banner_ansi() -> None:
    try:
        for line in BANNER_TITLE_LINES:
            _print_green(line, bold=True)
    except Exception:  # pragma: no cover - absolute fallback
        _print_plain(APP_NAME)

    _print_plain()
    _print_green(_SEPARATOR)
    _print_plain()
    _print_green(f"{APP_NAME} v{APP_VERSION}", bold=True)
    _print_plain(APP_TAGLINE)
    _print_plain()
    _print_plain("  ".join(f"[{icon}] {label}" for icon, label in APP_FEATURES))
    _print_plain()
    _print_green(_SEPARATOR)
    _print_plain()

    _print_plain(f"Python Version : {platform.python_version()}")
    _print_plain(f"Platform       : {platform.system()}")
    _print_plain(f"Execution Time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _print_plain(f"Working Dir    : {os.getcwd()}")
    _print_plain()
    _print_green(_SEPARATOR)
    _print_plain()


def startup_status(message: str, status: str = "ok") -> None:
    """Print a single enterprise-CLI-style startup progress line.

    Args:
        message: Description of the step, e.g. "Loading Configuration".
        status: One of "ok" (green check), "warn" (yellow warning), or
            "fail" (red cross). Defaults to "ok".
    """
    markers = {"ok": ("✓", _ANSI_GREEN), "warn": ("!", _ANSI_YELLOW), "fail": ("✗", _ANSI_RED)}
    symbol, color = markers.get(status, markers["ok"])
    line = f"[{symbol}] {message}"

    try:
        console = _get_console()
    except Exception:  # pragma: no cover - defensive
        console = None
    if console is not None:
        try:
            style = {"ok": "bold green", "warn": "bold yellow", "fail": "bold red"}[status if status in markers else "ok"]
            console.print(line, style=style)
            return
        except Exception:  # pragma: no cover - fall through to ANSI
            pass
    try:
        print(f"{color}{line}{_ANSI_RESET}")
    except Exception:  # pragma: no cover - defensive
        _print_plain(line)


def display_platform_ready(details: Dict[str, str], checklist: Sequence[str]) -> None:
    """Render the final "platform ready" summary panel.

    Unlike :func:`display_startup_banner`, this is meant to be called once
    real startup facts are known — after settings are loaded, agents are
    registered, and the workflow engine is initialized. Callers own the
    data: this module has no way to independently verify a provider,
    workflow, or agent count, so it only ever displays what it's given.

    Args:
        details: Ordered label -> value pairs, e.g. {"Provider": "aws",
            "Workflow": "full_workflow", "Run ID": "..."}.
        checklist: Labels of steps that completed successfully, rendered
            with a green checkmark, e.g. ["Loading Configuration", ...].
    """
    try:
        console = _get_console()
    except Exception:  # pragma: no cover - defensive
        console = None

    if console is not None:
        try:
            _display_platform_ready_rich(console, details, checklist)
            return
        except Exception:  # pragma: no cover - fall through to ANSI
            pass

    _display_platform_ready_ansi(details, checklist)


def _display_platform_ready_rich(
    console: "Console", details: Dict[str, str], checklist: Sequence[str]
) -> None:
    checklist_table = Table.grid(padding=(0, 3))
    checklist_table.add_column(justify="left")
    checklist_table.add_column(justify="left")
    items = list(checklist)
    for row_start in range(0, len(items), 2):
        row = items[row_start:row_start + 2]
        cells = [Text(f"✓ {item}", style="bold green", no_wrap=True, overflow="crop") for item in row]
        if len(cells) < 2:
            cells.append(Text(""))
        checklist_table.add_row(*cells)

    short_facts, long_facts = _split_facts(list(details.items()))
    body = Group(
        Align.center(_facts_grid_rich(short_facts, columns=3)),
        *(Align.center(line) for line in _long_facts_lines_rich(long_facts)),
        Text(""),
        Align.center(checklist_table),
        Text(""),
        Align.center(Text(APP_READY_HEADLINE, style="bold bright_green")),
        Align.center(Text(APP_READY_TAGLINE, style="dim green italic")),
        Text(""),
        Align.center(Text(f"★  {APP_FOOTER_TAGLINE}  ★", style="dim green")),
    )
    _panel(body, console=console)


def _display_platform_ready_ansi(details: Dict[str, str], checklist: Sequence[str]) -> None:
    _print_green(_SEPARATOR)
    _print_plain()
    for label, value in details.items():
        _print_plain(f"{label:<14}: {value}")
    _print_plain()
    for item in checklist:
        _print_green(f"[✓] {item}")
    _print_plain()
    _print_green(APP_READY_HEADLINE, bold=True)
    _print_plain(APP_READY_TAGLINE)
    _print_plain()
    _print_green(_SEPARATOR)
    _print_plain()
