"""
Manages the sorted report index at reports/index.json.

After each run, call update_index() to rebuild the index so the most
recent report always appears first.
"""

import json
import os
import re
from datetime import datetime, timezone

# Matches filenames like 20260610_120000_projectName.html / .json
_TS_RE = re.compile(r"^(\d{8}_\d{6})_(.+)\.(html|json)$")


def _parse_entry(filename: str, subdir: str) -> dict | None:
    """Return a parsed entry dict for a report filename, or None if unrecognised."""
    m = _TS_RE.match(filename)
    if not m:
        return None
    ts_str, project_slug, ext = m.group(1), m.group(2), m.group(3)
    try:
        ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        iso = ts.isoformat()
    except ValueError:
        iso = ts_str
    return {
        "timestamp":   ts_str,
        "iso":         iso,
        "project":     project_slug,
        "ext":         ext,
        "path":        f"{subdir}/{filename}",
    }


def update_index(reports_dir: str, project: str) -> str:
    """
    Scan reports/html/ and reports/json/, pair files by timestamp+project,
    sort newest-first, and write reports/index.json.

    Returns the path to the written index file.
    """
    html_dir = os.path.join(reports_dir, "html")
    json_dir = os.path.join(reports_dir, "json")

    # Collect all html entries keyed by (timestamp, project_slug)
    html_entries: dict[tuple, dict] = {}
    if os.path.isdir(html_dir):
        for fname in os.listdir(html_dir):
            e = _parse_entry(fname, "html")
            if e and e["ext"] == "html":
                html_entries[(e["timestamp"], e["project"])] = e

    # Collect all json entries keyed by (timestamp, project_slug)
    json_entries: dict[tuple, dict] = {}
    if os.path.isdir(json_dir):
        for fname in os.listdir(json_dir):
            e = _parse_entry(fname, "json")
            if e and e["ext"] == "json":
                json_entries[(e["timestamp"], e["project"])] = e

    # Union of all keys, build combined list
    all_keys = set(html_entries) | set(json_entries)
    combined = []
    for key in all_keys:
        ts_str, proj = key
        entry = {
            "timestamp": ts_str,
            "iso":       (html_entries.get(key) or json_entries[key])["iso"],
            "project":   proj,
        }
        if key in html_entries:
            entry["html"] = html_entries[key]["path"]
        if key in json_entries:
            entry["json"] = json_entries[key]["path"]
        combined.append(entry)

    # Sort newest first (reverse lexicographic on timestamp string — YYYYMMDD_HHMMSS)
    combined.sort(key=lambda e: e["timestamp"], reverse=True)

    index = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "project":    project,
        "count":      len(combined),
        "reports":    combined,
    }

    index_path = os.path.join(reports_dir, "index.json")
    os.makedirs(reports_dir, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    return index_path
