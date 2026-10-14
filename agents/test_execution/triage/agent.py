"""
TriageAgent — Phase 6.1: classifies every failed test of the latest Playwright run BEFORE anything is healed.

Verdicts: product_defect | test_defect.locator | test_defect.data | environment | flaky | known_issue | unknown,
each with the evidence it rests on (tools/triage/triage.py). Then (tools/triage/service.py):
  * environment  -> health check of the base URL; if healthy, one re-run (a second failure is re-classified);
  * failures     -> one --repeat-each=3 re-run; any pass makes it `flaky` (project.yaml healing.flaky_rerun);
  * unknown      -> one LLM call that must quote the error it relies on (healing.triage_llm), else stays unknown.

Writes test_execution/reports/triage.json (+ defects.json: the product_defect list, never healed). HealingAgent
reuses triage.json when it was written for the same report, so triage runs once per execution.
"""

import json
import os
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.shared import get_logger


class TriageAgent(BaseAgent):
    MODULE_NAME = "triage"

    def __init__(self, provider=None, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.triage")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        project_dir = os.path.join(_ASSETS_BASE, safe)
        reports_dir = os.path.join(project_dir, "test_execution", "reports")
        report_json = request.get("report_json") or find_latest_report(reports_dir)
        if not report_json:
            return {"module": "triage", "status": "skipped", "project": project_name,
                    "reason": "no Playwright JSON report — run ui_execution first"}
        result = run_triage(project_name, report_json, settings=self.settings, logger=self.logger,
                            reruns=request.get("triage_reruns", True))
        counts = result["counts"]
        self._log(f"Triage of {os.path.basename(report_json)}: {counts or 'no failures'}")
        return {"module": "triage", "status": "success", "project": project_name, "report": report_json,
                "counts": counts, "triage": os.path.join(reports_dir, "triage.json"),
                "defects": os.path.join(reports_dir, "defects.json")}


def run_triage(project_name: str, report_json: str, settings: Optional[dict] = None, logger=None,
               reruns: bool = True) -> Dict[str, Any]:
    """Classify, refine (health check / re-runs / LLM per project.yaml `healing`), and write triage.json and
    defects.json next to the report. Shared by TriageAgent and HealingAgent."""
    from tools.triage import service
    from tools.triage.triage import PRODUCT_DEFECT, save, triage_report

    safe = _safe_name(project_name)
    project_dir = os.path.join(_ASSETS_BASE, safe)
    reports_dir = os.path.join(project_dir, "test_execution", "reports")
    cfg = load_triage_config(project_dir)
    result = triage_report(report_json, project_dir)
    if result["tests"] and reruns:
        llm = None
        if cfg["triage_llm"]:
            try:
                from connectors.connector_registry import ConnectorRegistry
                from agents.test_execution.triage.prompt import TRIAGE_PROMPT
                llm = service.make_llm(ConnectorRegistry(settings or {}), TRIAGE_PROMPT)
            except Exception as exc:          # no LLM configured: unknown stays unknown
                if logger:
                    logger.warning(f"[Triage] LLM unavailable for ambiguous failures: {exc}")
        result = service.refine(
            result,
            rerun=service.make_rerun(project_name, settings),
            health=service.http_health(_base_url(project_dir)),
            llm=llm,
            flaky_rerun=cfg["flaky_rerun"],
        )
    result["refined"] = bool(result["tests"] and reruns)
    save(result, os.path.join(reports_dir, "triage.json"))
    defects = [t for t in result["tests"] if t["verdict"] == PRODUCT_DEFECT]
    with open(os.path.join(reports_dir, "defects.json"), "w", encoding="utf-8") as fh:
        json.dump(defects, fh, indent=2)
    return result


def load_triage_config(project_dir: str) -> Dict[str, Any]:
    """project.yaml `healing:` — flaky_rerun (default true), triage_llm (default true; needs connectors.llm)."""
    import yaml
    try:
        with open(os.path.join(project_dir, "project.yaml"), encoding="utf-8") as fh:
            raw = (yaml.safe_load(fh) or {}).get("healing")
    except Exception:
        raw = None
    raw = raw if isinstance(raw, dict) else {}
    return {"flaky_rerun": bool(raw.get("flaky_rerun", True)), "triage_llm": bool(raw.get("triage_llm", True))}


def _base_url(project_dir: str) -> str:
    import yaml
    try:
        with open(os.path.join(project_dir, "project.yaml"), encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:
        return ""
    url = (cfg.get("project") or {}).get("url") or cfg.get("url") or ""
    if not url:
        urls = [m.get("url") for m in cfg.get("modules") or [] if isinstance(m, dict) and m.get("url")]
        url = urls[0] if urls else ""
    return url


def find_latest_report(reports_dir: str) -> Optional[str]:
    json_dir = os.path.join(reports_dir, "json")
    if not os.path.isdir(json_dir):
        return None
    files = sorted((f for f in os.listdir(json_dir) if f.endswith("_results.json")), reverse=True)
    return os.path.join(json_dir, files[0]) if files else None


def load_fresh_triage(reports_dir: str, report_json: str) -> Optional[Dict[str, Any]]:
    """triage.json when it was written for this report (by TriageAgent earlier in the run), else None."""
    path = os.path.join(reports_dir, "triage.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if data.get("report") == os.path.basename(report_json) else None


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"
