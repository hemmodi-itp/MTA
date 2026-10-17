"""Unit tests for the Output Validation Engine (engines/validation/output.py) — no LLM."""

from engines.validation.output import assemble, deterministic_checks, ground_judgement, judge_payload, needs_judge

DOC_TEXT = ("Business Requirements Document\n1. Problem statement\nClinic patients cannot book appointments online, "
            "so receptionists handle every booking by phone.\n2. Scope\nOnline booking, reminders and cancellations. " + "word " * 80)


def _bundle(tmp_path, **over):
    (tmp_path / "AP-TC-001" / "downloads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "AP-TC-001/downloads/brd.docx.txt").write_text(DOC_TEXT, encoding="utf-8")
    b = {
        "bundle_id": "EV-TC-001", "test_id": "t1", "test_code": "TC-001", "criterion_code": "AC-01.1", "requirement_ref": "REQ-01",
        "title": "BRD generated as a Word document", "variant": "positive", "kind": "brd_test", "scored": True,
        "criterion_statement": "The system generates a BRD in DOCX format", "test_input": "Clinic booking problem",
        "expected_behavior": "A Word document with problem statement and scope", "execution_status": "completed",
        "failed_step": None, "error": None, "duration_ms": 52_000,
        "inputs": [{"step": 3, "action": "fill", "field": "Problem statement",
                    "value": "Clinic patients cannot book appointments online; receptionists handle bookings", "synthetic": False},
                   {"step": 4, "action": "fill", "field": "Project name", "value": "MTA Evaluation Project", "synthetic": True}],
        "observed": {"ui_output": "Your documents are ready", "page_change": "added", "page_text_excerpt": "...",
                     "messages": ["Documents generated successfully"], "reply": None, "http_response": None,
                     "documents": [{"file": "AP-TC-001/downloads/brd.docx", "name": "brd.docx", "format": "docx", "readable": True,
                                    "words": 120, "headings": ["1. Problem statement", "2. Scope"],
                                    "text_file": "AP-TC-001/downloads/brd.docx.txt", "text_excerpt": DOC_TEXT[:200]}]},
        "expectations": [{"expectation": "A Word document with problem statement and scope",
                          "pass_criteria": ["includes a problem statement", "includes the scope"]}],
        "observations": {"api_calls": 3, "api_failures": [], "slowest_call": {"method": "POST", "path": "/api/generate", "ms": 41_000},
                         "page_errors": []},
        "completeness": {"output_captured": True, "expected_output": "document", "missing": []},
    }
    b.update(over)
    return b


def _ids(checks):
    return {c["id"]: c["result"] for c in checks}


def test_document_checks_pass(tmp_path):
    r = _ids(deterministic_checks(_bundle(tmp_path), tmp_path))
    assert r == {"executed": "pass", "document_produced": "pass", "document_readable": "pass", "document_not_empty": "pass",
                 "document_format": "pass", "input_reflected": "pass", "no_server_errors": "pass"}


def test_missing_document_wrong_format_and_server_error_fail(tmp_path):
    b = _bundle(tmp_path, execution_status="failed", failed_step=7, error="no download was produced")
    b["observed"]["documents"] = []
    b["observations"]["api_failures"] = [{"method": "POST", "path": "/api/generate", "status": 502, "ms": 30000}]
    r = _ids(deterministic_checks(b, tmp_path))
    assert r["executed"] == "fail" and r["document_produced"] == "fail" and r["no_server_errors"] == "fail"
    b2 = _bundle(tmp_path, expected_behavior="The BRD is exported as a PDF", criterion_statement="The BRD can be exported",
                 expectations=[{"expectation": "The BRD is exported as a PDF", "pass_criteria": []}])
    b2["observed"]["documents"][0]["format"] = "docx"
    assert _ids(deterministic_checks(b2, tmp_path))["document_format"] == "fail"


def test_input_not_reflected_is_flagged(tmp_path):
    b = _bundle(tmp_path)
    b["inputs"][0]["value"] = "Warehouse forklift telemetry dashboards for logistics operators"
    check = next(c for c in deterministic_checks(b, tmp_path) if c["id"] == "input_reflected")
    assert check["result"] == "fail" and "forklift" in check["detail"]


def test_negative_rejection_and_time_limit(tmp_path):
    b = _bundle(tmp_path, variant="negative", expected_behavior="Rejects an empty form within 5 seconds")
    b["observed"]["documents"] = []
    b["observed"]["messages"] = ["Please fill all required fields"]
    b["completeness"]["expected_output"] = "ui_output"
    b["observations"]["slowest_call"] = {"ms": 800}
    r = _ids(deterministic_checks(b, tmp_path))
    assert r["rejected_visibly"] == "pass" and r["time_limit"] == "pass" and "document_produced" not in r
    b["observations"]["slowest_call"] = {"ms": 9000}
    assert _ids(deterministic_checks(b, tmp_path))["time_limit"] == "fail"


def test_reply_checks():
    b = {"execution_status": "completed", "variant": "positive", "observed": {"reply": "Traceback (most recent call last): ..."},
         "completeness": {"expected_output": "reply"}, "observations": {}, "inputs": [], "expectations": []}
    r = _ids(deterministic_checks(b, None))
    assert r["reply_present"] == "pass" and r["reply_not_error"] == "fail"


def test_judge_quotes_are_verified_and_score_capped(tmp_path):
    b = _bundle(tmp_path)
    raw = {"criteria_results": [
        {"criterion": "includes a problem statement", "result": "met", "quote": "Clinic patients cannot book appointments online"},
        {"criterion": "includes the scope", "result": "met", "quote": "Scope: booking, payments and analytics"}],  # invented
        "assessment": "meets", "score": 95, "reasoning": "All good."}
    j = ground_judgement(raw, b, tmp_path)
    assert [c["result"] for c in j["criteria_results"]] == ["met", "cannot_tell"]
    assert j["criteria_results"][0]["quote_verified"] and j["criteria_results"][1]["note"] == "quote not found in the output"
    assert j["ungrounded_quotes"] == 1 and j["assessment"] == "partially_meets" and j["score"] == 75


def test_payload_uses_full_document_text_and_hides_synthetic_inputs(tmp_path):
    p = judge_payload(_bundle(tmp_path), tmp_path)
    assert "receptionists handle every booking" in p["observed"]["documents"][0]["text"]
    assert [i["field"] for i in p["inputs_sent"]] == ["Problem statement"]
    assert p["pass_criteria"] == ["includes a problem statement", "includes the scope"]


def test_not_executed_bundle_is_not_validatable(tmp_path):
    b = _bundle(tmp_path, execution_status="not_executed", error="behind a login")
    assert not needs_judge(b) and deterministic_checks(b, tmp_path) == []
    r = assemble(b, [], None)
    assert r["status"] == "not_validatable" and "behind a login" in r["summary"]
    ok = assemble(_bundle(tmp_path), deterministic_checks(_bundle(tmp_path), tmp_path), None, "LLM down")
    assert ok["status"] == "validated" and ok["core_failures"] == [] and "judge unavailable" in ok["summary"]


def test_a_format_is_required_only_when_the_expectation_asks_for_that_file():
    from engines.validation.output import _FORMATS, _asks_for_format
    ask = lambda f, t: _asks_for_format(_FORMATS[f], t)
    assert ask("docx", "User exports the BRD, TSD, or one-pager as a DOCX file with diagrams embedded as images.")
    assert ask("pdf", "The report downloads a PDF")
    assert not ask("md", "User views side-by-side formatted previews of generated markdown documents and rendered Mermaid diagrams.")


# ── on-screen results, optional files, judge resilience ─────────────────────

CHROME = "BRD Agent Suite\nAI Document Generator\nDashboard\nNew Request\nHistory\nBRD\nTSD\nFlowchart"


def _views(tmp_path, bodies):
    out = []
    for name, body in bodies.items():
        (tmp_path / "AP-TC-001" / f"view-{name}.txt").write_text(CHROME + "\n" + body + "\nGenerated 2m ago", encoding="utf-8")
        out.append({"name": name, "text_file": f"AP-TC-001/view-{name}.txt"})
    return out


def test_a_file_collected_only_as_evidence_is_not_a_core_check(tmp_path):
    # a preview / history test on a Document Generator: the files are collected, but the test is about the screen
    b = _bundle(tmp_path, title="Side-by-side previews", expected_behavior="Formatted previews are shown")
    b["observed"]["documents"] = []
    b["observed"]["views"] = _views(tmp_path, {"BRD": DOC_TEXT, "Flowchart": "flowchart TD; A-->B"})
    b["completeness"] = {"output_captured": True, "expected_output": "document", "missing": [], "document_required": False}
    checks = {c["id"]: c for c in deterministic_checks(b, tmp_path)}
    assert "document_produced" not in checks or checks["document_produced"]["weight"] == "supporting"
    assert checks["document_not_empty"]["result"] == "pass" and "result shown on screen" in checks["document_not_empty"]["detail"]
    assert checks["input_reflected"]["result"] == "pass"                           # read from the on-screen result
    required = _bundle(tmp_path)
    required["observed"]["documents"] = []
    assert next(c for c in deterministic_checks(required, tmp_path) if c["id"] == "document_produced")["weight"] == "core"


def test_diagram_images_do_not_count_as_an_empty_document(tmp_path):
    b = _bundle(tmp_path)
    b["observed"]["documents"] = [{"name": "flowchart.png", "format": "png", "kind": "image", "readable": True, "words": 0}]
    b["observed"]["views"] = _views(tmp_path, {"BRD": DOC_TEXT})
    checks = {c["id"]: c for c in deterministic_checks(b, tmp_path)}
    assert checks["document_not_empty"]["result"] == "pass"          # TC-018 was flagged "0 words" for its PNGs


def test_judge_sees_each_text_once_without_page_chrome(tmp_path):
    from engines.validation.output import observed_corpus
    b = _bundle(tmp_path)
    b["observed"]["views"] = _views(tmp_path, {"BRD": DOC_TEXT, "Flowchart": "flowchart TD; Intake-->Review-->Approve"})
    corpus = observed_corpus(b, tmp_path)
    names = [v["name"] for v in corpus["result_views"]]
    assert names == ["Flowchart"]                                       # the BRD tab repeats brd.docx: sent once
    assert corpus["result_views"][0]["text"].startswith("flowchart TD") and "New Request" not in corpus["result_views"][0]["text"]


class _FlakyJudge:
    """Fails every call with more than one test (like a batch timing out); answers single-test calls, skipping none."""

    def __init__(self):
        self.calls = []

    def generate_json(self, prompt, schema=None, temperature=None):
        import json as _json
        import re as _re
        ids = sorted(set(_re.findall(r'"bundle_id": "(EV-[^"]+)"', prompt)))
        self.calls.append(ids)
        if len(ids) > 1:
            raise TimeoutError("Gemini JSON call: no reply within 180s")
        return _json.dumps({"judgements": [{"bundle_id": i, "assessment": "meets", "score": 90, "reasoning": "ok",
                                            "criteria_results": [{"criterion": "c", "result": "met",
                                                                  "quote": "Clinic patients cannot book appointments online"}]}
                                           for i in ids]})


def test_a_failed_batch_is_judged_test_by_test(tmp_path, monkeypatch):
    import agents.evaluation.output_validation.agent as ova
    judge = _FlakyJudge()
    agent = ova.OutputValidationAgent({})
    monkeypatch.setattr(agent._registry, "get_llm", lambda *a, **k: judge)
    monkeypatch.setattr(ova, "run_artifact_dir", lambda run_id: tmp_path)
    bundles = []
    for i in (1, 2, 3, 4):
        b = _bundle(tmp_path, bundle_id=f"EV-TC-00{i}", test_code=f"TC-00{i}")
        bundles.append(b)
    out = agent.execute({"evidence_collection": {"bundles": bundles}, "run_id": "r"}, {})
    results = out["output_validation"]["results"]
    assert all(r["judge"] and r["judge"]["assessment"] == "meets" for r in results)  # nobody left "judge unavailable"
    assert sorted(c[0] for c in judge.calls if len(c) == 1) == ["EV-TC-001", "EV-TC-002", "EV-TC-003", "EV-TC-004"]
