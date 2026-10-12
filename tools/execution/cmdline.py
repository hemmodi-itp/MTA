"""
cmdline.py — run `npx …` without a shell on every OS (Phase 4).

On Windows `npx` is `npx.cmd`. CreateProcess runs a .cmd/.bat through cmd.exe, and subprocess only quotes arguments
that contain spaces, so an unquoted `|` in `--grep "@smoke|@P0"` (or a suite grep `(M01_BS_001|M02_BS_001)`) became a
pipe: Playwright wrote no report and the run broke with EPIPE. resolve_cmd() resolves cmd[0] through PATH and, for a
.cmd/.bat target, returns one command line whose cmd.exe metacharacters are inside double quotes.
"""

import os
import shutil
from typing import List, Union

# cmd.exe metacharacters (plus space/tab, which need quoting anyway)
_CMD_META = set(' \t&|<>^()!"')


def cmd_exe_line(cmd: List[str]) -> str:
    """One command line for a .cmd/.bat target: every argument with a cmd.exe metacharacter is double-quoted
    (inner quotes doubled), which cmd.exe leaves literal and node's argv parser unquotes."""
    parts = []
    for arg in cmd:
        a = str(arg)
        parts.append('"' + a.replace('"', '""') + '"' if (not a or any(c in _CMD_META for c in a)) else a)
    return " ".join(parts)


def resolve_cmd(cmd: List[str]) -> Union[List[str], str]:
    """cmd with cmd[0] resolved to a full path; on Windows a .cmd/.bat target becomes a cmd.exe-safe string."""
    if not cmd:
        return cmd
    resolved = shutil.which(cmd[0])
    out = [resolved, *cmd[1:]] if resolved else list(cmd)
    if os.name == "nt" and str(out[0]).lower().endswith((".cmd", ".bat")):
        return cmd_exe_line(out)
    return out
