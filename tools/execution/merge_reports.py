"""
merge_reports.py — merge the blob reports of a sharded run (Phase 4.8).

    npx playwright merge-reports --config playwright.merge.config.ts <collected zips>

playwright.merge.config.ts declares only reporters (json, html, junit, MTA) driven by the same env vars
as a normal run (PW_JSON_REPORT, PW_HTML_REPORT, PW_JUNIT_REPORT, MTA_RESULTS_FILE). It never resolves a
base URL: the main config fails fast without one, and a merge has no target to test.

Every shard writes report-<i>.zip into its own folder (the blob reporter empties its output folder);
collect_blobs() copies them into one `_merge_input/` folder first, which is what merge-reports reads.

CLI (a CI merge job, after every shard job uploaded reports/blob/<run_id>/shard-<i>/):
    python -m tools.execution.merge_reports --project <name> --run <run_id>
"""

import argparse
import glob
import json
import os
import shutil
import sys
from typing import Dict, List, Tuple

MERGE_CONFIG = "playwright.merge.config.ts"


def collect_blobs(root: str) -> Tuple[str, List[str]]:
    """Copy every shard zip under *root* into root/_merge_input/ -> (input dir, zip names)."""
    target = os.path.join(root, "_merge_input")
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target, exist_ok=True)
    names: List[str] = []
    for z in sorted(glob.glob(os.path.join(root, "**", "*.zip"), recursive=True)):
        if os.path.dirname(os.path.abspath(z)) == os.path.abspath(target):
            continue
        name = os.path.basename(z)
        if name in names:   # two shards can't produce the same name, but never overwrite one
            name = f"{os.path.basename(os.path.dirname(z))}-{name}"
        shutil.copy2(z, os.path.join(target, name))
        names.append(name)
    return target, names


def merge_command(input_dir: str) -> List[str]:
    return ["npx", "playwright", "merge-reports", "--config", MERGE_CONFIG, input_dir.replace(os.sep, "/")]


def merge_env(base_env: Dict[str, str], *, json_path: str, html_dir: str, junit_path: str = "",
              mta_path: str = "") -> Dict[str, str]:
    env = {**base_env, "PW_JSON_REPORT": json_path, "PW_HTML_REPORT": html_dir}
    for key in ("PW_JUNIT_REPORT", "MTA_RESULTS_FILE", "PW_BLOB_DIR", "MTA_BLOB_ONLY"):
        env.pop(key, None)
    if junit_path:
        env["PW_JUNIT_REPORT"] = junit_path
    if mta_path:
        env["MTA_RESULTS_FILE"] = mta_path
    return env


def merge_blob_reports(root: str, env: Dict[str, str], run_proc, cwd: str = None):
    """Collect + merge. run_proc(cmd, cwd, env) -> (stdout, stderr, interrupted, returncode)
    (UIExecutionAgent passes its streaming runner). Returns (zip names, (stdout, stderr, interrupted, rc));
    with no zips at all the merge is skipped and rc is 1."""
    input_dir, names = collect_blobs(root)
    if not names:
        return names, ("", f"no blob reports under {root}", False, 1)
    return names, run_proc(merge_command(input_dir), cwd or os.getcwd(), env)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Merge the blob reports of a sharded MTA run")
    ap.add_argument("--project", required=True)
    ap.add_argument("--run", required=True, help="run id (the reports/blob/<run_id>/ folder)")
    args = ap.parse_args(argv)

    from agents.test_execution.ui_execution.agent import UIExecutionAgent

    out = UIExecutionAgent().execute({"project_name": args.project, "merge_run": args.run}, {})
    summary = {k: out.get(k) for k in ("status", "passed", "failed", "skipped", "flaky", "report_json",
                                       "report_html", "report_junit", "mta_results", "error")}
    print(json.dumps(summary, indent=2))
    return 0 if out.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
