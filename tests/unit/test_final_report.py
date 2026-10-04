"""Unit tests for the Final Evaluation Report (engines/report/final.py)."""

from engines.report.final import build_report, render_html, render_markdown


def _ctx(compliance=82.0, gates=None, **over):
    ctx = {
        "run_id": "run123", "github_url": "https://github.com/acme/brd-agent", "repo_full_name": "acme/brd-agent",
        "branch": "main", "commit_sha": "abcdef1234567", "mode": "brd_and_live", "live_url": "https://app.example.com",
        "brd_source": "repository", "brd_path": "docs/brd.pdf", "agent_profile": {"agent_name": "BRD Agent"},
        "score": {"compliance": compliance, "ci_low": 70.0, "ci_high": 90.0, "score_kind": "brd_compliance", "risk_level": "low",
                  "verification_depth": 0.6, "scoring_version": "compliance-v1.1", "excluded_requirements": [],
                  "gates": gates if gates is not None else [{"gate": "all", "level": "pass", "reason": "No blocking or warning conditions"}]},
        "requirements": [{"code": "REQ-01", "title": "Generate BRD", "priority": "high", "origin": "brd", "verdict": "verified",
                          "score": 0.9, "criteria": [{"code": "AC-01.1", "statement": "Generates a DOCX"}]}],
        "app_classification": {"app_type": "Document Generator", "components": [], "basis": "runtime + code",
                               "testing_strategy": [{"class": "Document Generator", "strategy": "Output testing"}]},
        "runtime_profile": {"app_type": "Document Generator", "pages_inspected": 3, "login": {"succeeded": True}},
        "pass_fail": {"counts": {"passed": 1, "failed": 1, "inconclusive": 0, "not_executed": 1, "tests": 3}, "pass_rate": 50.0,
                      "tests": [{"test_code": "TC-001", "title": "Generates", "criterion_code": "AC-01.1", "scored": True, "verdict": "passed",
                                 "score": 95, "strength": "E4", "reasons": []},
                                {"test_code": "TC-002", "title": "Risks <b>section</b>", "criterion_code": "AC-01.1", "scored": True,
                                 "verdict": "failed", "score": 10, "strength": "E4", "reasons": ["No risks section"],
                                 "artifacts": {"screenshot": "AP-TC-002/screenshot.png", "documents": [{"name": "brd.docx"}]}},
                                {"test_code": "TC-003", "title": "Fast", "criterion_code": "AC-02.1", "scored": True,
                                 "verdict": "not_executed", "reasons": ["latency claim"]}]},
        "brd_compliance": {"matrix": [{"code": "REQ-01", "scored": True, "criteria": [
            {"code": "AC-01.1", "statement": "Generates a DOCX", "resolved_verdict": "verified_pass", "strength": "E4", "basis": "runtime",
             "discrepancy": None, "runtime": {"tests": [{"test_code": "TC-001", "verdict": "passed", "score": 95, "strength": "E4"}]}}]}],
            "discrepancies": [], "evidence_mix": {"by_strength": {"E5": 0, "E4": 1, "E3": 0, "E2": 0, "E1": 0, "none": 0},
                                                  "runtime_share": 1.0, "credit_by_basis": {"runtime": 1.0, "code": 0.0}},
            "counts": {"criteria_without_evidence": 0}},
        "findings": [{"severity": "critical", "title": "Hard-coded secret", "file": "app.py", "start_line": 3, "fix": "use env"},
                     {"severity": "low", "title": "nit"}],
        "recommendations": [{"severity": "warning", "category": "failed_test", "summary": "Fix risks"}],
    }
    ctx.update(over)
    return ctx


def test_decision_rules():
    assert build_report(_ctx(82.0))["decision"]["outcome"] == "Compliant"
    warn = [{"gate": "runtime_inconclusive", "level": "warn", "reason": "x"}]
    assert build_report(_ctx(82.0, warn))["decision"]["outcome"] == "Compliant with warnings"
    assert build_report(_ctx(60.0))["decision"]["outcome"] == "Partially compliant"
    assert build_report(_ctx(40.0))["decision"]["outcome"] == "Not compliant"
    block = [{"gate": "critical_security", "level": "block", "reason": "secret in app.py"}]
    r = build_report(_ctx(95.0, block))["decision"]
    assert r["outcome"] == "Not compliant" and "secret in app.py" in r["reason"]
    assert build_report(_ctx(None))["decision"]["outcome"] == "Not assessable"


def test_sections_summary_and_limitations():
    rep = build_report(_ctx())
    assert rep["meta"]["repository"] == "acme/brd-agent" and rep["application"]["logged_in"]
    assert rep["runtime"]["failed"][0]["screenshot"] == "/api/runs/run123/execution-files/AP-TC-002/screenshot.png"
    assert rep["runtime"]["not_run"] == [{"reason": "latency claim", "count": 1}]
    assert [f["title"] for f in rep["findings"]] == ["Hard-coded secret"]  # only critical/high
    joined = " ".join(rep["summary"])
    assert "BRD Agent: Compliant. BRD compliance 82/100" in joined and "1 of 3 BRD tests passed" in joined
    assert any("not executed" in x for x in rep["limitations"])
    behind = build_report(_ctx(runtime_profile={"needs_credentials": True}, pass_fail=None, brd_compliance=None))
    assert any("behind a login" in x for x in behind["limitations"]) and behind["runtime"] is None
    brd_only = build_report(_ctx(mode="brd_only", pass_fail=None))
    assert any("not deployed" in x for x in brd_only["limitations"]) and brd_only["meta"]["live_url"] is None


def test_renderers_escape_untrusted_text():
    ctx = _ctx()
    ctx["requirements"][0]["title"] = "<script>alert(1)</script>"
    rep = build_report(ctx)
    page = render_html(rep)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "Risks &lt;b&gt;section&lt;/b&gt;" in page and page.startswith("<!doctype html>")
    md = render_markdown(rep)
    assert md.startswith("# Final Evaluation Report — BRD Agent") and "**Outcome: Compliant**" in md
    assert "**TC-002 failed** (AC-01.1)" in md and "[screenshot](/api/runs/run123/execution-files/AP-TC-002/screenshot.png)" in md
