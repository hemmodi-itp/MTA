"""
bugs.py — seeded-bug flag registry for the Buggy Shop benchmark app.

Every bug is OFF by default. Flags are read from the environment at call time
(never cached), so a running app or a test using monkeypatch.setenv picks up
changes immediately:

    BUG_07=1            enables BUG_07 only
    BUGS=all            enables every bug
    BUGS=BUG_01,BUG_07  enables a list (comma/space separated)
"""

import os
import re

ALL_BUGS: tuple[str, ...] = tuple(f"BUG_{i:02d}" for i in range(1, 23))

_TRUTHY = {"1", "true", "yes", "on"}


def _listed() -> set[str]:
    raw = os.environ.get("BUGS", "").strip()
    if not raw:
        return set()
    if raw.lower() == "all":
        return set(ALL_BUGS)
    return {tok.strip().upper() for tok in re.split(r"[,\s]+", raw) if tok.strip()}


def is_on(bug_id: str) -> bool:
    """True when *bug_id* (e.g. "BUG_07") is enabled via its own flag or BUGS."""
    bug_id = bug_id.upper()
    if os.environ.get(bug_id, "").strip().lower() in _TRUTHY:
        return True
    return bug_id in _listed()


def enabled_bugs() -> list[str]:
    """Sorted list of currently enabled bug ids."""
    return [b for b in ALL_BUGS if is_on(b)]
