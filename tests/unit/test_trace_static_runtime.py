"""
Requirement traceability, split into a static pass (RequirementTraceabilityAgent, no runtime inputs) and
apply_runtime_evidence (brd_compliance, after Pass/Fail): together they must equal the old single combined pass.
Also: LLM failures become llm_unavailable (never silent insufficient evidence), one criterion's crash is isolated,
the second verifier sample is skipped only when the first is decisive, and the absence protocol.
"""

import copy
import json
import threading
from pathlib import Path

import pytest

import agents.evaluation.requirement_traceability.agent as rt_agent
from agents.evaluation.requirement_traceability.agent import RequirementTraceabilityAgent
from agents.evaluation.requirement_traceability.tools import apply_runtime_evidence, runtime_evidence
from engines.repo_intel.indexer import index_repository
from engines.trace.absence import absence_check
from engines.trace.decide import decide, roll_up

SERVER_PY = '''from fastapi import FastAPI
from . import service

app = FastAPI()


@app.post("/api/runs/{run_id}/export/{doc}")
async def export_document(run_id: str, doc: str):
    return service.export_docx(run_id, doc)
'''

SERVICE_PY = '''import os


def export_docx(run_id: str, doc: str):
    """Convert the markdown to DOCX with pandoc."""
    return run_pandoc(run_id, doc)


def run_pandoc(run_id, doc):
    return f"{run_id}/{doc}.docx"


def list_runs():
    return []


def delete_run(run_id):
    return None


def rename_run(run_id, name):
    return name
'''

REQUIREMENTS = [
    {"id": "r1", "code": "REQ-01", "title": "Export documents", "description": "Users export the BRD as DOCX.",
     "priority": "high", "verifiability": "both", "kind": "functional",
     "criteria": [{"id": "c11", "code": "AC-01.1", "statement": "The user can export a document as DOCX", "weight": 1},
                  {"id": "c12", "code": "AC-01.2", "statement": "Exports are emailed to the user", "weight": 1}]},
    {"id": "r2", "code": "REQ-02", "title": "Audit log", "description": "Every export is logged.",
     "priority": "medium", "verifiability": "both", "kind": "functional",
     "criteria": [{"id": "c21", "code": "AC-02.1", "statement": "Each export writes an audit entry", "weight": 1}]},
]
TESTS = [{"id": "t1", "code": "TC-001", "criterion_code": "AC-01.1"},
         {"id": "t2", "code": "TC-002", "criterion_code": "AC-01.2"}]
RESULTS = [{"id": "t1", "status": "failed", "strength": "E5", "decided_by": "deterministic", "judge_score": 0},
           {"id": "t2", "status": "passed", "strength": "E4", "decided_by": "judge", "judge_score": 9}]

IMPLEMENTED = {"status": "implemented", "rationale": "export_document calls export_docx which runs pandoc.",
               "citations": [{"file": "webapp/server.py", "start_line": 8, "end_line": 10, "symbol": "export_document",
                              "claim": "export_document calls service.export_docx"},
                             {"file": "webapp/service.py", "start_line": 4, "end_line": 6, "symbol": "export_docx",
                              "claim": "export_docx converts to DOCX via run_pandoc"}],
               "looked_for": [], "need_more": [], "confidence": "high"}
ABSENT = {"status": "not_implemented", "rationale": "No email sending anywhere.", "citations": [],
          "looked_for": ["smtp", "send_email", "sendgrid"], "need_more": [], "confidence": "medium"}


class FakeLLM:
    """Scripted verifier: answers by the criterion in the prompt; AC-02.1 always fails."""

    def __init__(self, fail_codes=("AC-02.1",), answers=None):
        self.fail_codes = set(fail_codes)
        self.answers = answers or {"AC-01.1": IMPLEMENTED, "AC-01.2": ABSENT}
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, llm, prompt, required_keys=None, schema=None, temperature=None, **kw):
        with self.lock:
            self.calls.append((prompt, temperature))
        if '{"criteria": [{"code"' in prompt:
            return {"criteria": [{"code": "AC-01.1", "terms": ["export", "docx", "pandoc"]},
                                 {"code": "AC-01.2", "terms": ["email", "smtp"]},
                                 {"code": "AC-02.1", "terms": ["audit"]}]}
        code = next(c for c in ("AC-01.1", "AC-01.2", "AC-02.1") if f"Acceptance criterion {c}" in prompt)
        if code in self.fail_codes:
            raise TimeoutError("LLM timed out")
        return copy.deepcopy(self.answers[code])

    def verifier_calls(self, code):
        return [t for p, t in self.calls if f"Acceptance criterion {code}" in p]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "webapp").mkdir()
    (tmp_path / "webapp" / "server.py").write_text(SERVER_PY, encoding="utf-8")
    (tmp_path / "webapp" / "service.py").write_text(SERVICE_PY, encoding="utf-8")
    return tmp_path


def _request(repo: Path, **extra):
    idx = index_repository(repo)
    return {"requirements": copy.deepcopy(REQUIREMENTS), "repo_graph": idx.graph, "code_chunks": idx.chunks,
            "repo_dir": str(repo), "repo_full_name": "o/r", "commit_sha": "a" * 40, "repo_model": idx.repo_model,
            "repo_coverage": {"truncated": False}, **extra}


def _run(monkeypatch, repo, fake, **extra):
    monkeypatch.setattr(rt_agent, "generate_json", fake)
    agent = RequirementTraceabilityAgent({})
    req = _request(repo, llm=object(), **extra)
    return agent.execute(req, {}), req


def _old_combined(static_trace, requirements, tests, results):
    """The pre-split agent's final assembly, verbatim in behaviour: decide each criterion with its runtime evidence,
    attach negative_search, collect static + runtime evidence, roll requirements up (mutating them)."""
    runtime = runtime_evidence(tests, results)
    entries = {e["code"]: e for e in static_trace["criteria"]}
    reqs = copy.deepcopy(requirements)
    cv, ev = [], []
    for req in reqs:
        out = []
        for c in req["criteria"]:
            e = entries[c["code"]]
            v = decide(c, req, copy.deepcopy(e["static_a"]), copy.deepcopy(e["static_b"]), runtime.get(c["code"], []))
            v["negative_search"] = e["negative_search"]
            evidence = list(e["static_evidence"]) + [{"method": "runtime", **x} for x in runtime.get(c["code"], [])]
            out.append((c, v, evidence))
        rolled = roll_up(req, [(c, v) for c, v, _ in out])
        req.update({"verdict": rolled["verdict"], "score": rolled["score"], "status": rolled["legacy_status"]})
        for c, v, evidence in out:
            cv.append({**v, "code": c["code"], "criterion_id": c.get("id"), "requirement_code": req["code"]})
            ev += [{**x, "criterion_id": c.get("id")} for x in evidence]
    return cv, ev, reqs


_EXTRA_KEYS = ("samples", "sample_b", "llm_error")  # bookkeeping the split adds; not verdict content


def _strip(v):
    return {k: x for k, x in v.items() if k not in _EXTRA_KEYS}


def test_static_pass_is_runtime_free_and_returns_the_new_keys(monkeypatch, repo):
    out, _ = _run(monkeypatch, repo, FakeLLM())
    assert set(out) >= {"criterion_verdicts", "evidence_items", "traced_requirements", "static_trace", "llm_failures"}
    assert "requirements" not in out  # renamed: must not collide with brd_builder's key
    json.dumps(out["static_trace"])  # serialisable
    with_runtime, _ = _run(monkeypatch, repo, FakeLLM(), test_cases=TESTS, execution_results=RESULTS)
    assert [_strip(v) for v in with_runtime["criterion_verdicts"]] == [_strip(v) for v in out["criterion_verdicts"]]
    assert all(v["best_strength"] not in ("E4", "E5") for v in out["criterion_verdicts"])
    assert not any(e["method"] == "runtime" for e in out["evidence_items"])


def test_static_plus_apply_runtime_equals_the_old_combined_pass(monkeypatch, repo):
    out, req = _run(monkeypatch, repo, FakeLLM())
    trace_before = copy.deepcopy(out["static_trace"])
    reqs_before = copy.deepcopy(REQUIREMENTS)
    merged = apply_runtime_evidence(out["static_trace"], REQUIREMENTS, TESTS, RESULTS)
    old_cv, old_ev, old_reqs = _old_combined(out["static_trace"], REQUIREMENTS, TESTS, RESULTS)

    assert [_strip(v) for v in merged["criterion_verdicts"]] == [_strip(v) for v in old_cv]
    assert merged["evidence_items"] == old_ev
    for new, old in zip(merged["traced_requirements"], old_reqs):
        assert {k: new[k] for k in ("code", "verdict", "score", "status")} == {k: old[k] for k in ("code", "verdict", "score", "status")}
    # inputs untouched, new structures returned
    assert out["static_trace"] == trace_before and REQUIREMENTS == reqs_before
    by = {v["code"]: v for v in merged["criterion_verdicts"]}
    assert by["AC-01.1"]["verdict"] == "verified_fail" and by["AC-01.1"]["static_verdict"] == "implemented_static"
    assert by["AC-01.2"]["verdict"] == "verified_pass"
    assert by["AC-02.1"]["verdict"] == "llm_unavailable"  # no runtime test reached it
    # with no runtime evidence, apply reproduces the static result exactly
    again = apply_runtime_evidence(out["static_trace"], REQUIREMENTS, [], [])
    assert again["criterion_verdicts"] == out["criterion_verdicts"]
    assert again["traced_requirements"] == out["traced_requirements"]


def test_llm_failure_is_llm_unavailable_and_the_step_is_partial(monkeypatch, repo):
    out, _ = _run(monkeypatch, repo, FakeLLM())
    v = next(v for v in out["criterion_verdicts"] if v["code"] == "AC-02.1")
    assert v["verdict"] == "llm_unavailable" and v["llm_failed"] is True and v["credit"] == 0
    assert "timed out" in v["llm_error"]
    assert out["llm_failures"] == 1 and out["status"] == "partial" and "llm_unavailable" in out["error"]
    r2 = next(r for r in out["traced_requirements"] if r["code"] == "REQ-02")
    assert r2["verdict"] == "llm_unavailable" and r2["score"] is None and r2["llm_unavailable"] == 1


def test_one_criterion_crash_does_not_kill_the_step(monkeypatch, repo):
    def boom(*a, **k):
        raise RuntimeError("index exploded")
    monkeypatch.setattr(rt_agent.CodeIndex, "lookup", boom)
    fake = FakeLLM(fail_codes=(), answers={"AC-01.1": {**IMPLEMENTED, "status": "partial", "need_more": ["x_y"]},
                                           "AC-01.2": ABSENT, "AC-02.1": ABSENT})
    out, _ = _run(monkeypatch, repo, fake)
    by = {v["code"]: v for v in out["criterion_verdicts"]}
    assert by["AC-01.1"]["verdict"] == "llm_unavailable" and "RuntimeError" in by["AC-01.1"]["llm_error"]
    assert by["AC-01.2"]["verdict"] in ("not_implemented", "insufficient_evidence")
    assert out["status"] == "partial"


def test_second_sample_skipped_only_when_first_is_decisive(monkeypatch, repo):
    fake = FakeLLM(fail_codes=())
    fake.answers["AC-02.1"] = ABSENT
    out, _ = _run(monkeypatch, repo, fake)
    assert fake.verifier_calls("AC-01.1") == [0.2]          # decisive: B skipped, A pinned at 0.2
    assert sorted(fake.verifier_calls("AC-01.2")) == [0.2, 0.7]  # absence always gets a second opinion
    v = next(v for v in out["criterion_verdicts"] if v["code"] == "AC-01.1")
    assert v["verdict"] == "implemented_static" and v["samples"] == 1 and v["sample_b"].startswith("skipped")
    assert out["llm_failures"] == 0 and out["status"] == "success"


def test_untrusted_content_is_fenced(monkeypatch, repo):
    fake = FakeLLM(fail_codes=())
    fake.answers["AC-02.1"] = ABSENT
    _run(monkeypatch, repo, fake)
    verifier = next(p for p, _ in fake.calls if "Acceptance criterion AC-01.1" in p)
    assert '<untrusted_content source="repository">' in verifier and '<untrusted_content source="brd">' in verifier
    # the wiring paths sit inside a fence too
    paths = verifier.split("## How the retrieved code is wired")[1].split("## Retrieved code")[0]
    assert "<untrusted_content" in paths
    expansion = next(p for p, _ in fake.calls if '{"criteria": [{"code"' in p)
    assert expansion.count("<untrusted_content source=") == 2


def test_absence_protocol():
    terms = ["email", "smtp"]
    assert absence_check(8, ["smtp", "send_email"], terms, {}, {}) == (True, None)
    ok, why = absence_check(8, [], terms, {}, {})
    assert not ok and "concrete" in why
    ok, why = absence_check(2, ["smtp"], terms, {}, {})
    assert not ok and "candidate" in why
    ok, why = absence_check(8, ["smtp"], terms, {}, {"truncated": True, "truncation_reason": "tree truncated"})
    assert not ok and "truncated" in why
    cov = {"files_indexed": 100, "unfetched_source": ["src/mail/smtp_client.go"], "unfetched_source_count": 1}
    ok, why = absence_check(8, ["smtp"], terms, cov, {})
    assert not ok and "smtp_client.go" in why
    cov = {"files_indexed": 100, "unfetched_source": ["src/billing/invoice.go"], "unfetched_source_count": 1}
    assert absence_check(8, ["smtp"], terms, cov, {}) == (True, None)


def test_absence_blocked_by_coverage_becomes_insufficient_with_reason():
    req = {"code": "R", "verifiability": "both"}
    a = {"status": "not_implemented", "valid_citations": 0, "negative_search_ok": False,
         "absence_reason": "the repository listing was truncated", "rationale": "nothing found"}
    v = decide({"code": "AC"}, req, a, None, [])
    assert v["verdict"] == "insufficient_evidence" and "truncated" in v["rationale"]
