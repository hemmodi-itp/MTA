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
        """Phase 11: report["quality"] (summary, gates, not-tested, defects with severity + evidence, risk areas,
        trend, coverage dashboard, 29119-3 summary, CSV/XLSX matrix, Jira/ADO exports) when project.yaml
        `reporting.enhanced` is on; gates evaluated when `quality_gates` is set. Never raises."""
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
            # the execution step's own rows (spec_file, test_title, tc_id, tags, pw_status, browser, attachments) —
            # report["test_execution_report"]["results"] keeps only a display subset of them
            exec_out = (outputs or {}).get("execution") or (outputs or {}).get("ui_execution") or {}
            results = exec_out.get("results") or report["test_execution_report"].get("results") or []
            trace = report.get("traceability")
            plans = _load(os.path.join(pdir, "test_creation", "test_plans.json")) or {}
            suite = _load(os.path.join(pdir, "test_creation", "test_suite.json")) or {}
            triage = _load(os.path.join(reports_dir, "triage.json"))
            aq = ((outputs or {}).get("agent_quality_testing") or {}).get("agent_quality")
            test_cases = _load(os.path.join(pdir, "test_creation", "test_cases.json"))
            summary = qs.compute_summary(results, trace, plans, suite, triage, aq, test_cases)
            gate_result = qs.evaluate_gates(summary, gates)
            from tools.reporting import insights
            stamp = now.strftime('%Y%m%d_%H%M%S')
            html_dir = os.path.join(reports_dir, "html")
            rel = lambda path: os.path.relpath(path, html_dir).replace(os.sep, "/")   # noqa: E731 — links from the HTML
            csv_dir = os.path.join(reports_dir, "csv")
            os.makedirs(csv_dir, exist_ok=True)
            csv_path = os.path.join(csv_dir, f"{stamp}_{safe}.traceability.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(qs.traceability_csv(trace))
            xlsx_path = qs.traceability_xlsx(trace, os.path.join(csv_dir, f"{stamp}_{safe}.traceability.xlsx"))
            run_id = report["test_execution_report"].get("run_id") or stamp
            environment = str(raw.get("environment") or "")
            defects = qs.build_defects(results, triage, plans, run=run_id, environment=environment)
            summary["defects_by_severity"] = insights.defects_by_severity(defects)
            not_tested = qs.not_tested(trace)
            risks = insights.risk_areas(results, trace, plans)
            history = insights.record_history(reports_dir, summary, gate_result, results, run=stamp)
            comp = os.path.join(pdir, "test_comprehension")
            spec_texts = _spec_texts(os.path.join(pdir, "test_creation", "test_scripts"))
            coverage = insights.coverage_dashboard(
                results, trace, plans, test_cases, _load(os.path.join(pdir, "test_creation", "locator_map.json")),
                _load(os.path.join(comp, "app_map.json")), _load(os.path.join(comp, "api_inventory.json")), spec_texts)
            exports = {}
            if defects:
                ddir = os.path.join(reports_dir, "defects")
                os.makedirs(ddir, exist_ok=True)
                key = str((raw.get("reporting") or {}).get("jira_project") or "QA")
                for kind, payload in (("jira", insights.jira_issues(defects, key)), ("ado", insights.ado_work_items(defects))):
                    path = os.path.join(ddir, f"{stamp}_{safe}.{kind}.json")
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(payload, fh, indent=2)
                    exports[kind] = rel(path)
            deviations = [w for step in (outputs or {}).values() if isinstance(step, dict) for w in step.get("warnings") or []][:10]
            tsr = insights.test_summary_report(safe, summary, gate_result, results, defects, not_tested, coverage, risks,
                                               deviations)
            tsr_path = os.path.join(reports_dir, "summary", f"{stamp}_{safe}.test_summary_report.md")
            os.makedirs(os.path.dirname(tsr_path), exist_ok=True)
            with open(tsr_path, "w", encoding="utf-8") as fh:
                fh.write(insights.summary_markdown(tsr, safe))
            report["quality"] = {"summary": summary, "gates": gate_result, "not_tested": not_tested,
                                 "defects": defects, "potential_defects": qs.potential_defects(test_cases),
                                 "risk_areas": risks, "trend": insights.trend(history), "coverage": coverage,
                                 "test_summary_report": tsr, "exports": exports,
                                 "csv_path": rel(csv_path), "xlsx_path": rel(xlsx_path) if xlsx_path else None,
                                 "tsr_path": rel(tsr_path)}
            return gate_result
        except Exception as exc:
            self.logger.warning(f"[ReportingAgent] Quality section failed (non-fatal): {exc}")
            return None


def _spec_texts(scripts_dir: str) -> dict:
    """{relative spec path: text} — the coverage dashboard looks for locator keys, pages and API paths in them."""
    out = {}
    for root, _dirs, files in os.walk(scripts_dir):
        for f in files:
            if f.endswith(".spec.ts"):
                try:
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        out[os.path.relpath(os.path.join(root, f), scripts_dir)] = fh.read()
                except OSError:
                    continue
    return out
