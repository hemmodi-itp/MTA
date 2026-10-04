"""
Unit tests for the deterministic core of the MTA evaluation pipeline (no LLM, no database):
verdict rules and roll-up, compliance scoring, citation validation and wiring, BRD grounding,
BRD path normalisation, repository indexing and exact-symbol lookup.
"""

from pathlib import Path

import pytest

from engines.repo_intel.indexer import index_repository
from engines.scoring.v1 import score
from engines.trace.citations import FileCache, is_wired, nodes_at, validate_citation
from engines.trace.decide import decide, roll_up
from engines.trace.retrieve import CodeIndex
from tools.agent_eval.brd_source import BrdIndex, normalize_brd_path

# ── a tiny repo: FastAPI route → service function; frontend fetch → route ────────────────────

APP_PY = '''from fastapi import FastAPI
from . import service

app = FastAPI()


@app.post("/api/runs/{run_id}/export/{doc}")
async def export_document(run_id: str, doc: str):
    return service.export_docx(run_id, doc)
'''

SERVICE_PY = '''import os

API_KEY = os.environ.get("GEMINI_API_KEY")


def export_docx(run_id: str, doc: str):
    """Convert the markdown to DOCX with pandoc."""
    return run_pandoc(run_id, doc)


def run_pandoc(run_id, doc):
    return f"{run_id}/{doc}.docx"
'''

API_TS = '''export async function exportDoc(runId: string, doc: string) {
  return fetch(`/api/runs/${runId}/export/${doc}`, { method: "POST" });
}

export class DocumentRenderer {
  render() { return "ok"; }
}
'''


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "webapp").mkdir()
    (tmp_path / "webapp" / "server.py").write_text(APP_PY, encoding="utf-8")
    (tmp_path / "webapp" / "service.py").write_text(SERVICE_PY, encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "api.ts").write_text(API_TS, encoding="utf-8")
    return tmp_path


# ── repository intelligence ──────────────────────────────────────────────────────────────────

def test_index_links_route_handler_and_frontend_call(repo):
    idx = index_repository(repo)
    g = idx.graph
    route = "route:POST /api/runs/*/export/*"
    assert route in g.nodes
    assert (route, "exposes", "symbol:webapp/server.py#export_document") in g.edges
    assert ("symbol:webapp/server.py#export_document", "calls", "symbol:webapp/service.py#export_docx") in g.edges
    assert ("file:frontend/api.ts", "calls_api", route) in g.edges
    assert "config:GEMINI_API_KEY" in g.nodes
    assert "symbol:frontend/api.ts#DocumentRenderer" in g.nodes


def test_lookup_prefers_exact_symbol_over_generic_file_names(repo):
    idx = index_repository(repo)
    hits = CodeIndex(idx.graph, idx.chunks).lookup(["server.py", "service.export_docx", "service.py"])
    assert hits and hits[0][0].symbol == "export_docx"


# ── citations ────────────────────────────────────────────────────────────────────────────────

def test_citation_validation(repo):
    idx = index_repository(repo)
    files = FileCache(repo)
    ok, _ = validate_citation({"file": "webapp/service.py", "start_line": 6, "end_line": 8, "symbol": "export_docx",
                               "claim": "`export_docx` calls run_pandoc"}, files, graph=idx.graph)
    assert ok
    bad_file, why = validate_citation({"file": "webapp/nope.py", "start_line": 1, "end_line": 2}, files)
    assert not bad_file and "not in repository" in why
    bad_lines, _ = validate_citation({"file": "webapp/service.py", "start_line": 500, "end_line": 510}, files)
    assert not bad_lines
    wrong_symbol, _ = validate_citation({"file": "webapp/service.py", "start_line": 11, "end_line": 12,
                                         "symbol": "does_not_exist", "claim": "x"}, files, graph=idx.graph)
    assert not wrong_symbol
    # lines inside a function body, citing the enclosing function by name
    enclosed, _ = validate_citation({"file": "webapp/service.py", "start_line": 8, "end_line": 8,
                                     "symbol": "export_docx", "claim": "returns"}, files, graph=idx.graph)
    assert enclosed


def test_wiring_reaches_an_entry_point(repo):
    idx = index_repository(repo)
    keys = nodes_at(idx.graph, "webapp/service.py", 6, 8)
    assert is_wired(idx.graph, keys) is not None  # service function ← handler ← route


# ── verdicts ─────────────────────────────────────────────────────────────────────────────────

REQ = {"code": "REQ-01", "priority": "high", "verifiability": "both"}
CRIT = {"code": "AC-01.1", "weight": 1}
IMPL = {"status": "implemented", "valid_citations": 2, "wired": "route POST /x", "negative_search_ok": True}


def test_runtime_refutation_beats_static_pass():
    v = decide(CRIT, REQ, IMPL, IMPL, [{"outcome": "refutes", "strength": "E4", "summary": "failed"}])
    assert v["verdict"] == "verified_fail" and v["credit"] == 0


def test_static_implemented_and_wired_is_e3():
    v = decide(CRIT, REQ, IMPL, IMPL, [])
    assert v["verdict"] == "implemented_static" and v["best_strength"] == "E3" and v["credit"] == 0.75


def test_uncited_claim_earns_nothing():
    v = decide(CRIT, REQ, {**IMPL, "valid_citations": 0}, None, [])
    assert v["verdict"] == "insufficient_evidence" and v["credit"] == 0


def test_absence_needs_a_negative_search():
    v = decide(CRIT, REQ, {"status": "not_implemented", "valid_citations": 0, "negative_search_ok": False}, None, [])
    assert v["verdict"] == "insufficient_evidence"


def test_runtime_only_criterion_caps_at_partial_statically():
    v = decide(CRIT, {**REQ, "verifiability": "runtime"}, IMPL, IMPL, [])
    assert v["resolved_verdict"] == "partial"


def test_disagreeing_samples_take_the_conservative_verdict():
    v = decide(CRIT, REQ, IMPL, {"status": "not_implemented"}, [])
    assert v["verdict"] == "contested" and v["agreement"] == 0.6


def test_roll_up_excludes_non_technical_criteria():
    ok = decide(CRIT, REQ, IMPL, IMPL, [])
    nt = decide(CRIT, {**REQ, "verifiability": "non_technical"}, None, None, [])
    out = roll_up(REQ, [(CRIT, ok), ({"code": "AC-01.2", "weight": 1}, nt)])
    assert out["verdict"] == "implemented" and out["score"] == 0.75


# ── scoring ──────────────────────────────────────────────────────────────────────────────────

def _req(code, priority, verdict_credit, origin="brd"):
    return {"code": code, "title": code, "priority": priority, "origin": origin, "confidence": 1.0,
            "verifiability": "both", "criteria": [{"code": f"{code}.1", "weight": 1}],
            "verdict": "implemented" if verdict_credit else "insufficient_evidence"}


def test_insufficient_evidence_counts_as_zero_not_excluded():
    reqs = [_req("R1", "medium", 0.75), _req("R2", "medium", 0.0)]
    verdicts = [{"code": "R1.1", "verdict": "implemented_static", "resolved_verdict": "implemented_static",
                 "credit": 0.75, "best_strength": "E3"},
                {"code": "R2.1", "verdict": "insufficient_evidence", "resolved_verdict": "insufficient_evidence",
                 "credit": 0.0, "best_strength": "E1"}]
    out = score(reqs, verdicts, [], {"security": 100}, {"runtime_possible": False})
    assert out["compliance"] == 37.5  # (0.75 + 0) / 2, not 75


def test_descriptive_requirements_are_not_scored():
    reqs = [_req("R1", "high", 0.75, origin="descriptive")]
    out = score(reqs, [{"code": "R1.1", "verdict": "implemented_static", "credit": 0.75, "best_strength": "E3"}], [],
                None, {})
    assert out["compliance"] is None and any(g["gate"] == "no_scorable_requirements" for g in out["gates"])


def test_critical_scanner_finding_blocks():
    reqs = [_req("R1", "high", 0.75)]
    v = [{"code": "R1.1", "verdict": "implemented_static", "credit": 0.75, "best_strength": "E3"}]
    out = score(reqs, v, [{"severity": "critical", "source": "scanner", "title": "Hard-coded secret", "file": "a.py",
                           "start_line": 1}], None, {})
    assert any(g["level"] == "block" for g in out["gates"]) and out["risk_level"] == "high"


def test_scoring_is_reproducible():
    reqs = [_req(f"R{i}", "high", 0.75) for i in range(5)]
    v = [{"code": f"R{i}.1", "verdict": "implemented_static", "credit": 0.75 if i % 2 else 0.375, "best_strength": "E3"}
         for i in range(5)]
    assert score(reqs, v, [], None, {}) == score(reqs, v, [], None, {})


# ── BRD grounding / paths ────────────────────────────────────────────────────────────────────

def test_brd_quote_grounding():
    ix = BrdIndex("## 4.1\nUser can export the BRD, TSD, or one-pager as a DOCX with diagrams embedded as images.")
    assert ix.grounded("User can export the BRD, TSD, or one-pager as a DOCX with diagrams embedded as images")
    assert ix.grounded("**user can export the BRD, TSD or one-pager as a DOCX with diagrams embedded as images**")
    assert not ix.grounded("The system must sync with Salesforce every night")


def test_brd_path_normalisation():
    assert normalize_brd_path("https://github.com/o/r/blob/main/docs/My%20BRD.pdf", "o/r") == "docs/My BRD.pdf"
    assert normalize_brd_path("/docs/BRD.md") == "docs/BRD.md"
    with pytest.raises(ValueError):
        normalize_brd_path("https://github.com/other/repo/blob/main/x.pdf", "o/r")
    with pytest.raises(ValueError):
        normalize_brd_path("../../etc/passwd")


def test_positive_plus_unsure_keeps_positive_one_level_lower():
    unsure = {"status": "insufficient_evidence", "valid_citations": 0, "wired": None, "negative_search_ok": False}
    v = decide(CRIT, REQ, unsure, IMPL, [])
    assert v["verdict"] == "implemented_static" and v["best_strength"] == "E2" and v["agreement"] == 0.6
