"""
visual.py — Phase 7.2 baseline approval for the generated @visual specs.

The first run of a visual test records its baseline and passes (annotation `visual-baseline`). After an intended UI
change, a person reviews the diff images in the Playwright report and approves the new look:

    python -m tools.nonfunctional.visual approve --project <name> [--grep "<title part>"]

which re-runs the @visual tests with --update-snapshots, so the current screenshots become the baselines.
"""

from __future__ import annotations

import argparse
import re
from typing import List, Optional


def approve(project: str, grep: str = "") -> dict:
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    pattern = "@visual" + (f".*{re.escape(grep)}|{re.escape(grep)}.*@visual" if grep else "")
    return UIExecutionAgent().execute({"project_name": project, "headless": True, "grep": pattern,
                                       "update_snapshots": True, "spec_files": ["nfr/nfr_visual.spec.ts"]}, {})


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Approve visual baselines (Phase 7.2).")
    ap.add_argument("command", choices=["approve"])
    ap.add_argument("--project", required=True)
    ap.add_argument("--grep", default="")
    args = ap.parse_args(argv)
    out = approve(args.project, args.grep)
    print(f"approved: {out.get('passed', 0)} passed, {out.get('failed', 0)} failed — report {out.get('report_json')}")
    return 0 if not out.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
