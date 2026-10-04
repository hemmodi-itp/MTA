"""
FinalReportAgent — the Final Evaluation Report of a run.

Deterministic (engines/report/final.py), no LLM: assembles what Components 1-8 recorded into one
report — decision (Compliant / with warnings / Partially / Not compliant / Not assessable), executive
summary, what was evaluated, the compliance matrix, runtime results with failure screenshots,
code-vs-runtime discrepancies, critical findings, gates, recommendations, evidence coverage,
limitations and method — rendered as JSON, Markdown and a standalone printable HTML page. All three
are stored with the run (Run.finalReport) and served by /api/runs/:runId/report.
"""

from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.evaluation.final_report.tools import build_report, render_html, render_markdown
from tools.shared import get_logger


class FinalReportAgent(BaseAgent):
    MODULE_NAME = "final_report"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.final_report")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        if not request.get("score"):
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "no compliance score to report", "final_report": None}
        report = build_report(request)
        d = report["decision"]
        emit(f"Final report: {d['outcome']}"
             + (f" — compliance {d['compliance']:.0f}/100" if d["compliance"] is not None else "")
             + f"; {len(report['recommendations'])} recommendation(s), {len(report['limitations'])} stated limitation(s).",
             "success" if d["outcome"] in ("Compliant", "Compliant with warnings") else "warning")
        return {"module": self.MODULE_NAME, "status": "success",
                "final_report": {"data": report, "markdown": render_markdown(report), "html": render_html(report)}}
