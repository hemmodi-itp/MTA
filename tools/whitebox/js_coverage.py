"""
js_coverage.py — Phase 8.3 frontend: summarise the V8 JS coverage the test fixture records (MTA_JS_COVERAGE=<dir>).

Without source maps (v8-to-istanbul is not installed) the measure is per script and per function: a function counts
as covered when any test ran it (V8 `functions[].ranges[0].count > 0`). Inline <script> blocks are keyed by page URL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def summarize(folder: str) -> Dict[str, Any]:
    scripts: Dict[str, Dict[str, set]] = {}
    for f in Path(folder).glob("*.json"):
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for e in entries:
            url = e.get("url") or "inline"
            slot = scripts.setdefault(url, {"all": set(), "hit": set()})
            for fn in e.get("functions") or []:
                ranges = fn.get("ranges") or [{}]
                key = (fn.get("functionName") or "(anonymous)", ranges[0].get("startOffset"))
                slot["all"].add(key)
                if (ranges[0].get("count") or 0) > 0:
                    slot["hit"].add(key)
    per = {u: {"functions": len(v["all"]), "covered": len(v["hit"]),
               "pct": round(100.0 * len(v["hit"]) / len(v["all"]), 1) if v["all"] else None}
           for u, v in sorted(scripts.items())}
    total = sum(p["functions"] for p in per.values())
    hit = sum(p["covered"] for p in per.values())
    return {"scripts": per, "functions": total, "covered": hit,
            "function_pct": round(100.0 * hit / total, 1) if total else None}
