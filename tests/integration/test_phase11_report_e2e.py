"""
Phase 11 acceptance, end to end: a real Playwright run on buggy_shop with BUG_18 on (one genuine product defect),
then TriageAgent and ReportingAgent exactly as the workflow calls them. Checks: the report renders offline (no
external URL), every summary number links to its section, the defect carries real evidence files, the Jira/ADO
exports, XLSX matrix and 29119-3 summary are written, quality gates fail and main.gate_exit returns 1.

Run:  python -m pytest tests/integration/test_phase11_report_e2e.py -v -s
"""

import json
import os
import re
import shutil

import pytest

import tests.integration.test_phase5_oracles_e2e as p5
from tools.constants import PROJECTS_BASE

pytestmark = p5.pytestmark
_real_projects_base = p5._real_projects_base      # same fixture: the real runner reads the real projects folder

GATES = """reporting:
  enhanced: true
  jira_project: SHOP
quality_gates:
  p0_pass_rate: 100
  requirement_coverage: 90
  max_flaky_rate: 50
"""


def test_report_with_a_real_defect(monkeypatch):
    from agents.test_execution.reporting.agent import ReportingAgent
    from agents.test_execution.triage.agent import TriageAgent
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS
    import main

    try:
        server = AppServer(APPS["buggy_shop"], port=p5._free_port(), bugs=["BUG_18"]).start()
    except Exception as exc:  # pragma: no cover — environment
        pytest.skip(f"buggy_shop did not start: {exc}")
    pdir = p5._project(server.base_url)
    with open(os.path.join(pdir, "project.yaml"), "a", encoding="utf-8") as fh:
        fh.write(GATES)
    from contracts.artifacts import save_artifact          # as script generation leaves it
    save_artifact("test_plans", os.path.join(pdir, "test_creation", "test_plans.json"), {"P5_BS_001": p5.PLAN})
    try:
        out = UIExecutionAgent().execute({"project_name": p5.PROJECT, "headless": True}, {})
        tri = TriageAgent().execute({"project_name": p5.PROJECT, "triage_reruns": False}, {})
        rep = ReportingAgent().execute({"project_name": p5.PROJECT}, {
            "run_id": "p11", "workflow_name": "e2e", "errors": [],
            "execution_trace": [{"step": "ui_execution", "status": "success"}, {"step": "triage", "status": "success"}],
            "outputs": {"ui_execution": out, "triage": tri}})
    finally:
        server.stop()
    try:
        assert tri["counts"].get("product_defect") == 1, tri
        paths = [v for v in rep.values() if isinstance(v, str) and v.endswith((".json", ".html"))]
        report = json.load(open(next(p for p in paths if p.endswith(".json")), encoding="utf-8"))
        q = report["quality"]
        # gates: requirement coverage has no data (no requirements) -> FAIL, and the CLI exit code says so
        assert q["gates"]["verdict"] == "FAIL"
        assert main.gate_exit({"reporting": {"quality_gates": q["gates"]}}) == 1
        # the defect: severity, plan steps, evidence files that exist
        d = q["defects"][0]
        assert d["title"].startswith(p5.STRONG) and d["severity"] in ("medium", "low", "high", "critical")
        assert d["steps"] and "Name is required" in d["expected"]
        html_dir = os.path.join(pdir, "test_execution", "reports", "html")
        ev = d["evidence"]
        assert ev.get("screenshot") and os.path.exists(ev["screenshot"])
        assert ev.get("trace") or ev.get("video")
        assert q["summary"]["defects_by_severity"][d["severity"]] == 1
        for key in ("xlsx_path", "tsr_path"):
            assert os.path.exists(os.path.normpath(os.path.join(html_dir, q[key]))), key
        jira = json.load(open(os.path.normpath(os.path.join(html_dir, q["exports"]["jira"])), encoding="utf-8"))
        assert jira[0]["fields"]["project"]["key"] == "SHOP"
        assert q["risk_areas"] and q["risk_areas"][0]["failed"] >= 1
        assert q["coverage"]["browser"] and "not measured" in q["coverage"]["code"]
        html = open(next(p for p in paths if p.endswith(".html")), encoding="utf-8").read()
        for anchor in ("defects", "risk", "coverage", "tsr"):
            assert f'id="{anchor}"' in html, anchor
        assert 'href="#defects"' in html and "Do not release" in html
        external = [u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', html)]
        assert not external, f"report must render offline, found {external[:3]}"
    finally:
        if not os.environ.get("MTA_KEEP_E2E"):
            shutil.rmtree(os.path.join(PROJECTS_BASE, p5.PROJECT), ignore_errors=True)
