"""
ReportingAgent — pure Python, no LLM.

Reads workflow state, assembles the report dict via tools/test_execution/reports/report_writer,
generates HTML via tools/test_execution/reports/html_report, and writes:

  reports/html/{YYYYMMDD_HHMMSS}_{project}.html
  reports/json/{YYYYMMDD_HHMMSS}_{project}.json

After writing, updates reports/index.json (sorted newest-first) via
tools/test_execution/reports/index_manager.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, Optional

from agents.base_agent import BaseAgent
from agents.test_execution.reporting.tools import build_html_report, update_index, build_report_dict
from tools.test_execution.reports.report_writer import build_failures_log_text
from tools.catalog.catalog_manager import stamp_execution_results, update_catalog
from tools.logger_config import get_logger
from tools.requirements.traceability import refresh_project as refresh_traceability
from tools.requirements.traceability import report_section as traceability_report_section

from tools.constants import PROJECTS_BASE as _ASSETS_BASE


def _safe_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


class ReportingAgent(BaseAgent):
    def __init__(self, provider=None, settings: Optional[dict] = None):
        self.logger = get_logger("agent.reporting")
        self.settings = settings or {}

    def execute(self, request: dict, state: dict) -> Dict[str, str]:
        self.logger.info("Invoking ReportingAgent")

        project_name    = request.get("project_name", "unknown")
        run_id          = state.get("run_id", "")
        workflow        = state.get("workflow_name", request.get("workflow", ""))
        execution_trace = state.get("execution_trace", [])
        errors          = state.get("errors", [])
        all_outputs     = state.get("outputs", {})
        outputs         = {k: v for k, v in all_outputs.items() if k != "reporting"}

        # ── Assemble report dict (pure Python, no LLM) ───────────
        now    = datetime.now(timezone.utc)
        report = build_report_dict(
            project_name    = project_name,
            run_id          = run_id,
            workflow        = workflow,
            execution_trace = execution_trace,
            errors          = errors,
            outputs         = outputs,
            generated_at    = now,
        )

        # ── Determine output paths ────────────────────────────────
        safe        = _safe_name(project_name)

        # ── Phase 1.2: requirements traceability (rebuilt from artifacts; keeps
        # the latest per-test results UIExecutionAgent folded in). Omitted when
        # requirements.enabled is off; a failure never fails reporting.
        try:
            trace = refresh_traceability(safe, request)
            if trace is not None:
                report["traceability"] = traceability_report_section(trace)
                s = trace.summary
                self.logger.info(
                    f"[ReportingAgent] Traceability — {s.get('acs_covered')}/{s.get('acs_automatable')} "
                    f"automatable AC(s) covered, {len(report['traceability']['uncovered'])} with no test, "
                    f"{s.get('tests_unlinked')} unlinked test(s)")
        except Exception as exc:
            self.logger.warning(f"[ReportingAgent] Traceability section failed (non-fatal): {exc}")

        # ── Stamp real per-test results back onto test_suite.json + refresh
        # the human-readable catalog. ReportingAgent runs unconditionally
        # right after ui_execution/healing (always_run: true), so this is the
        # one place guaranteed to see whatever fraction of the suite actually
        # completed — the catalog otherwise stays permanently blank because
        # nothing else in the pipeline ever writes last_result/last_run.
        try:
            exec_results = report["test_execution_report"].get("results") or []
            if exec_results:
                project_dir = os.path.join(_ASSETS_BASE, safe)
                stamped = stamp_execution_results(project_dir, exec_results)
                if stamped:
                    update_catalog(project_name)
                    self.logger.info(f"[ReportingAgent] Catalog refreshed — {stamped} spec(s) stamped")
        except Exception as exc:
            self.logger.warning(f"[ReportingAgent] Catalog refresh failed (non-fatal): {exc}")

        reports_dir = os.path.join(_ASSETS_BASE, safe, "test_execution", "reports")
        gate_result = self._quality_section(report, outputs, safe, reports_dir, now)
        ts          = now.strftime("%Y%m%d_%H%M%S")
        base_name   = f"{ts}_{safe}"

        html_dir     = os.path.join(reports_dir, "html")
        json_dir     = os.path.join(reports_dir, "json")
        failures_dir = os.path.join(reports_dir, "failures")
        os.makedirs(html_dir, exist_ok=True)
        os.makedirs(json_dir, exist_ok=True)
        os.makedirs(failures_dir, exist_ok=True)

        html_path     = os.path.join(html_dir, f"{base_name}.html")
        json_path     = os.path.join(json_dir, f"{base_name}.json")
        failures_path = os.path.join(failures_dir, f"{base_name}.log")

        # ── Write JSON ────────────────────────────────────────────
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        # ── Write HTML ────────────────────────────────────────────
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(build_html_report(report))

        # ── Write failures digest — persisted reference grouping every
        # failure by root cause (see build_failure_summary), and echoed to
        # the console/logs/agent.log in real time via self.logger so a
        # failing run's cause is visible without waiting for the report ──
        failures_text = build_failures_log_text(report)
        with open(failures_path, "w", encoding="utf-8") as f:
            f.write(failures_text)
        for group in report["test_execution_report"].get("failure_summary") or []:
            self.logger.warning(
                f"[ReportingAgent] {group['count']}x failure — {group['signature']} "
                f"(affected: {', '.join(group['test_case_ids'])})"
            )

        # ── Update sorted index (newest first) ───────────────────
        index_path = update_index(reports_dir, project_name)

        self.logger.info(f"[ReportingAgent] JSON     : {json_path}")
        self.logger.info(f"[ReportingAgent] HTML     : {html_path}")
        self.logger.info(f"[ReportingAgent] Failures : {failures_path}")
        self.logger.info(f"[ReportingAgent] Index    : {index_path}")
        self.logger.info("ReportingAgent completed")

        return {
            "module":            "reporting",
            "response":          "report generated",
            "report_path":       json_path,
            "html_report_path":  html_path,
            "failures_log_path": failures_path,
            "index_path":        index_path,
            "quality_gates":     gate_result,
            "details": {
                "steps_executed":  state.get("completed_steps", []),
                "workflow_status": report["workflow_status"],
                "test_execution":  report["test_execution_report"],
                "outputs":         outputs,
            },
        }

    def _quality_section(self, report: dict, outputs: dict, safe: str, reports_dir: str, now: datetime) -> Optional[dict]:
        """Phase 11-lean: report["quality"] (summary, gates, not-tested, defects, traceability CSV) when
        project.yaml `reporting.enhanced` is on; gates evaluated when `quality_gates` is set. Never raises."""
        try:
            from tools.reporting import summary as qs
            pdir = os.path.join(_ASSETS_BASE, safe)
            raw = qs.load_project_yaml(pdir)
            gates = qs.gates_config(raw)
            if not (qs.enhanced_enabled(raw) or gates):
                return None

            def _load(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        return json.load(fh)
                except (OSError, ValueError):
                    return None
            results = report["test_execution_report"].get("results") or []
            trace = report.get("traceability")
            plans = _load(os.path.join(pdir, "test_creation", "test_plans.json")) or {}
            suite = _load(os.path.join(pdir, "test_creation", "test_suite.json")) or {}
            triage = _load(os.path.join(reports_dir, "triage.json"))
            aq = ((outputs or {}).get("agent_quality_testing") or {}).get("agent_quality")
            test_cases = _load(os.path.join(pdir, "test_creation", "test_cases.json"))
            summary = qs.compute_summary(results, trace, plans, suite, triage, aq, test_cases)
            gate_result = qs.evaluate_gates(summary, gates)
            csv_dir = os.path.join(reports_dir, "csv")
            os.makedirs(csv_dir, exist_ok=True)
            csv_path = os.path.join(csv_dir, f"{now.strftime('%Y%m%d_%H%M%S')}_{safe}.traceability.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(qs.traceability_csv(trace))
            report["quality"] = {"summary": summary, "gates": gate_result, "not_tested": qs.not_tested(trace),
                                 "defects": qs.build_defects(results, triage, plans),
                                 "potential_defects": qs.potential_defects(test_cases),
                                 "csv_path": os.path.relpath(csv_path, os.path.join(reports_dir, "html"))}
            return gate_result
        except Exception as exc:
            self.logger.warning(f"[ReportingAgent] Quality section failed (non-fatal): {exc}")
            return None
