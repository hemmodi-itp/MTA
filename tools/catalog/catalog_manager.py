"""
catalog_manager.py — human-readable test-case lookup catalog.

Recomputed fresh from business_scenarios.json + test_suite.json on every
call and overwritten in place at a single fixed path per project. Never
appended, never timestamped, no intermediate JSON persisted — those two
source files are already the cumulative ground truth (scenario IDs and
spec IDs are upserted, never duplicated), so recomputing from them
reproduces every past row plus new ones in the same file automatically.
"""

import csv
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from tools.constants import PROJECTS_BASE as _ASSETS_BASE

_CSV_COLUMNS = [
    "scenario_id", "module_id", "module_name", "title", "description",
    "status", "last_result", "spec_file", "last_run", "generation_mode",
]


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"


def _load_json_or_empty(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f) or {}


def build_catalog_rows(project_dir: str) -> List[Dict[str, Any]]:
    """Join business_scenarios.json + test_suite.json into catalog rows.

    One row per scenario_id. status is derived fresh from disk every call:
      - "no_test_yet"  — scenario exists, no spec entry in test_suite.json
      - "generated"    — spec entry exists and its file is present on disk
      - "missing_file" — spec entry exists but the file is gone from disk
    """
    scenarios_path = os.path.join(project_dir, "test_comprehension", "business_scenarios.json")
    suite_path = os.path.join(project_dir, "test_creation", "test_suite.json")
    scripts_root = os.path.join(project_dir, "test_creation", "test_scripts")

    scenarios = _load_json_or_empty(scenarios_path).get("scenarios", [])
    specs = _load_json_or_empty(suite_path).get("specs", [])
    specs_by_id = {s.get("spec_id"): s for s in specs if s.get("spec_id")}

    rows = []
    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        spec = specs_by_id.get(sid)

        if spec is None:
            status, last_result, spec_file, last_run, generation_mode = "no_test_yet", None, None, None, None
        else:
            spec_file = spec.get("file")
            file_exists = bool(spec_file) and os.path.exists(os.path.join(scripts_root, spec_file))
            status = "generated" if file_exists else "missing_file"
            last_result = spec.get("last_result")
            last_run = spec.get("last_run")
            generation_mode = spec.get("generation_mode")

        objective = sc.get("business_objective", "") or ""
        description = objective[:120] + ("…" if len(objective) > 120 else "")

        rows.append({
            "scenario_id": sid,
            "module_id": sc.get("module_id") or "",
            "module_name": sc.get("module_name") or "",
            "title": sc.get("title", ""),
            "description": description,
            "status": status,
            "last_result": last_result or "",
            "spec_file": spec_file or "",
            "last_run": last_run or "",
            "generation_mode": generation_mode or "",
        })

    rows.sort(key=lambda r: r["scenario_id"])
    return rows


def write_catalog_exports(project_dir: str, rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """Overwrite the two fixed catalog files for this project. Never
    appends, never timestamps — same path every call, fully recomputed."""
    out_dir = os.path.join(project_dir, "test_creation")
    os.makedirs(out_dir, exist_ok=True)

    csv_path = os.path.join(out_dir, "test_catalog.csv")
    md_path = os.path.join(out_dir, "test_catalog.md")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in _CSV_COLUMNS})

    md_lines = [
        "# Test Case Catalog",
        "",
        f"Total: **{len(rows)} scenario(s)**",
        "",
        "| " + " | ".join(_CSV_COLUMNS) + " |",
        "|" + "|".join(["---"] * len(_CSV_COLUMNS)) + "|",
    ]
    for row in rows:
        md_lines.append(
            "| " + " | ".join(str(row.get(col, "")).replace("|", "\\|") for col in _CSV_COLUMNS) + " |"
        )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    return {"csv": csv_path, "markdown": md_path}


def stamp_execution_results(project_dir: str, results: List[Dict[str, Any]]) -> int:
    """Write last_result/last_run onto matching test_suite.json spec entries
    from real per-test execution results (business_scenario_id/test_case_id
    ties a result back to a spec_id). The catalog reads these fields, but
    nothing else in the pipeline ever populates them post-generation — this
    is that missing write. Returns the number of specs updated."""
    suite_path = os.path.join(project_dir, "test_creation", "test_suite.json")
    suite = _load_json_or_empty(suite_path)
    specs = suite.get("specs", [])
    if not specs or not results:
        return 0

    specs_by_id = {s.get("spec_id"): s for s in specs if s.get("spec_id")}
    today = datetime.now(timezone.utc).date().isoformat()

    updated = 0
    for r in results:
        sid = r.get("business_scenario_id") or r.get("test_case_id") or ""
        spec = specs_by_id.get(sid)
        if not spec:
            continue
        status = r.get("status", "")
        spec["last_result"] = "passed" if status in ("pass", "passed", "success") else (status or "failed")
        spec["last_run"] = today
        updated += 1

    if updated:
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump(suite, f, indent=2, ensure_ascii=False)
    return updated


def update_catalog(project_name: str) -> Dict[str, Any]:
    """Entry point: recompute and overwrite the catalog for one project."""
    safe = _safe_name(project_name)
    project_dir = os.path.join(_ASSETS_BASE, safe)
    rows = build_catalog_rows(project_dir)
    paths = write_catalog_exports(project_dir, rows)
    return {"rows": len(rows), **paths}
