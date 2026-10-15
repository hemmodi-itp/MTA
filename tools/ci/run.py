"""
run.py — Phase 10.6: the one CI entry point (ci/github-actions.yml and ci/azure-pipelines.yml call it).

    python -m tools.ci.run --project <name> --stage pr|nightly|release [--git-base origin/main]
                           [--start-app buggy_shop --port 8765] [--order-check] [--browsers chromium,firefox]

    pr        health check -> smoke tests + the tests a change impacts (Phase 10.5) + every P0, chromium
    nightly   burn-in admission of new / healed specs (Phase 10.1) -> the whole suite on execution.matrix,
              sharded per execution.shards -> optional order-independence check (10.3) -> fingerprint saved
    release   the whole suite on execution.matrix; quality gates decide

Every stage then triages failures and writes the report (quality gates, quarantine — quarantined tests never gate).
Exit code: 0 passed, 1 a quality gate failed (or the run failed), 3 the environment is blocked (health check).
Writes test_execution/reports/ci/<stage>_<ts>.json with the artifacts to upload (HTML, JSON, JUnit, traces).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.execution import quarantine as qz

ROOT = Path(__file__).resolve().parents[2]


def _settings() -> dict:
    import yaml
    try:
        return yaml.safe_load((ROOT / "workflows" / "settings.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def run_stage(project: str, stage: str, git_base: str = "", browsers: Optional[List[str]] = None,
              order_check: bool = False) -> Dict[str, Any]:
    from agents.test_execution.reporting.agent import ReportingAgent
    from agents.test_execution.triage.agent import TriageAgent
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    from tools.constants import PROJECTS_BASE
    from tools.execution import admission, selective

    settings = _settings()
    pdir = Path(PROJECTS_BASE) / project
    summary: Dict[str, Any] = {"project": project, "stage": stage, "started": datetime.now(timezone.utc).isoformat()}
    request: Dict[str, Any] = {"project_name": project, "headless": True, "run_id": f"ci-{stage}"}
    if browsers:
        request["browsers"] = browsers

    if stage == "pr":
        git_files = selective.git_changed(git_base) if git_base else None
        sel = selective.select(pdir, git_files=git_files)
        summary["selection"] = {"full": sel["full"], "impacted": len(sel["tests"]), "changed": sel["changed"]}
        request["browsers"] = browsers or ["chromium"]
        if not sel["full"]:
            request["grep"] = "@smoke" + (f"|{sel['grep']}" if sel["grep"] else "")
    elif stage == "nightly":
        summary["admission"] = admission.admit(str(pdir), project)

    out = UIExecutionAgent(settings=settings).execute(request, {})
    summary["execution"] = {k: out.get(k) for k in ("status", "passed", "failed", "flaky", "skipped", "report_json",
                                                   "report_html", "report_junit", "error")}
    outputs: Dict[str, Any] = {"ui_execution": out}
    if out.get("status") == "environment_blocked":
        summary["exit_code"] = 3
        summary["health"] = out.get("health")
        return summary
    if stage == "nightly" and order_check:
        specs = sorted({str(r.get("spec_file", "")).replace("\\", "/").split("test_scripts/")[-1]
                        for r in out.get("results") or [] if r.get("spec_file")})
        summary["order_check"] = admission.order_check(str(pdir), project, specs)

    tri = TriageAgent(settings=settings).execute({"project_name": project, "report_json": out.get("report_json"),
                                                  "triage_reruns": stage != "pr"}, {})
    outputs["triage"] = tri
    rep = ReportingAgent(settings=settings).execute({"project_name": project}, {
        "run_id": request["run_id"], "workflow_name": f"ci_{stage}", "errors": [],
        "execution_trace": [{"step": "ui_execution", "status": out.get("status")}, {"step": "triage", "status": tri.get("status")}],
        "outputs": outputs})
    gates = rep.get("quality_gates") or {}
    summary["triage"] = tri.get("counts")
    summary["gates"] = gates
    summary["report"] = {k: v for k, v in rep.items() if isinstance(v, str) and v.endswith((".html", ".json"))}
    if stage in ("nightly", "release") and out.get("status") == "success":
        summary["fingerprint"] = str(selective.save_fingerprint(pdir))
    summary["exit_code"] = exit_code(out, gates, qz.load(str(pdir)))
    return summary


def exit_code(execution: Dict[str, Any], gates: Dict[str, Any], quarantine: Dict[str, Any]) -> int:
    """3 environment blocked; 1 the run broke, a gate failed, or (no gates configured) a gating test failed; else 0.
    Quarantined tests never decide it."""
    if execution.get("status") == "environment_blocked":
        return 3
    if execution.get("status") not in ("success", "skipped"):
        return 1
    if gates.get("verdict"):
        return 1 if gates["verdict"] == "FAIL" else 0
    gating, _ = qz.split_results(execution.get("results") or [], quarantine)
    return 1 if any(qz._status(r) == "failed" for r in gating) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--stage", choices=["pr", "nightly", "release"], required=True)
    ap.add_argument("--git-base", default="")
    ap.add_argument("--browsers", default="")
    ap.add_argument("--order-check", action="store_true")
    ap.add_argument("--start-app", default="", help="start a benchmark app for the run (demo / self-test)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    os.chdir(ROOT)
    server = None
    if args.start_app:
        from tools.benchmark.app_server import AppServer
        from tools.benchmark.apps import APPS
        server = AppServer(APPS[args.start_app], port=args.port).start()
    try:
        summary = run_stage(args.project, args.stage, args.git_base,
                            [b for b in args.browsers.split(",") if b] or None, args.order_check)
    finally:
        if server is not None:
            server.stop()
    from tools.constants import PROJECTS_BASE
    out_dir = Path(PROJECTS_BASE) / args.project / "test_execution" / "reports" / "ci"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.stage}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    ex = summary.get("execution") or {}
    print(f"CI {args.stage}: {ex.get('status')} — {ex.get('passed')} passed, {ex.get('failed')} failed, "
          f"{ex.get('flaky')} flaky; gates {(summary.get('gates') or {}).get('verdict', 'n/a')}; exit {summary['exit_code']}")
    for g in (summary.get("gates") or {}).get("gates") or []:
        if not g["ok"]:
            print(f"  gate FAILED: {g['gate']} = {g['actual']} (need {'<=' if g.get('kind') == 'max' else '>='} {g['threshold']})")
    if summary["exit_code"] == 3:
        print(f"  environment blocked: {ex.get('error')}")
    print(f"CI summary: {path}")
    return int(summary["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
