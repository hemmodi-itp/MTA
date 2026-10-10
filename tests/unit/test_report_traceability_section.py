"""Phase 1.2 — the report lists every AC with zero tests (with the reason) and the tests linked to no AC."""

import json

from tools.requirements import traceability as tr
from tools.requirements.models import RequirementsDoc
from tools.test_execution.reports.html_report import build_html_report


def _trace():
    ac = lambda i, t="ui": {"id": i, "statement": f"<b>{i}</b> statement", "testability": t,
                            "testability_reason": "r", "priority": "P1"}
    doc = RequirementsDoc.model_validate({"requirements": [{"id": "REQ-01", "title": "Login", "module_id": "M01",
                                                            "acceptance_criteria": [ac("AC-01.1"), ac("AC-01.2", "api")]}]})
    plans = {"M01_BS_001": {"tests": [
        {"name": "p", "tc_id": "M01_TC_001", "ac_ids": ["AC-01.1"], "ac_link": "direct", "title": "AC-01.1 p"}]},
             "M01_BS_002": {"tests": [{"name": "q", "tc_id": "M01_TC_002", "ac_ids": [], "title": "q"}]}}
    suite = [{"spec_id": "M01_BS_001", "module_id": "M01", "file": "M01/t.spec.ts"},
             {"spec_id": "M01_BS_002", "module_id": "M01", "file": "M01/u.spec.ts"}]
    trace = tr.build(doc, [{"scenario_id": "M01_BS_001", "ac_ids": ["AC-01.1"]},
                           {"scenario_id": "M01_BS_002", "title": "Change theme"}], plans, suite)
    trace, _ = tr.apply_results(trace, [{"tc_id": "M01_TC_001", "pw_status": "expected"}])
    return trace


def _report(section):
    return {"project": "p", "workflow_status": {"steps": []}, "artifacts_generated": {},
            "test_execution_report": {}, "healing_report": None, "errors_and_validation": {},
            **({"traceability": section} if section else {})}


def test_html_section_lists_uncovered_acs_with_reasons_and_unlinked_tests():
    html = build_html_report(_report(tr.report_section(_trace())))
    assert "Requirements Traceability" in html
    assert "1 AC(s) with no test" in html
    assert "not_supported:api" in html and "AC-01.2" in html
    assert "Tests linked to no acceptance criterion (1)" in html and "M01_TC_002" in html
    assert "&lt;b&gt;AC-01.1&lt;/b&gt;" in html and "<b>AC-01.1</b>" not in html    # statements are escaped
    assert "50.0%" in html                                                         # 1 of 2 automatable covered


def test_html_report_without_traceability_is_unchanged():
    assert "Requirements Traceability" not in build_html_report(_report(None))


def test_section_is_json_serialisable():
    json.dumps(tr.report_section(_trace()))
