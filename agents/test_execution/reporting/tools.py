"""
tools.py — tool surface for ReportingAgent.

Re-exports the tools/test_execution/reports/ pipeline functions so agent.py
has a single, clear import point.
"""

from tools.test_execution.reports.html_report import build_html_report
from tools.test_execution.reports.index_manager import update_index
from tools.test_execution.reports.report_writer import build_report_dict

__all__ = [
    "build_html_report",
    "update_index",
    "build_report_dict",
]
