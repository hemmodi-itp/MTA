"""BrdBuilderAgent: criterion grounding / verifiability / self-generated provenance, explicit limitations,
runtime_profile as live evidence, agent claims, preview-based auto-detection."""

import json
from pathlib import Path

import pytest

import agents.comprehension.brd_builder.agent as brd_agent
from agents.comprehension.brd_builder.agent import BrdBuilderAgent, normalize_requirements
from tools.agent_eval import brd_source, live_discovery
from tools.agent_eval.brd_source import BrdIndex
from tools.agent_eval.schemas import BRD_DOCUMENT, BRD_SELECTION, REQUIREMENTS

BRD = """# Invoice Builder — Business Requirements Document
## 4. Functional requirements
FR-01 The user can create an invoice by entering the customer name, the amount and the due date.
- The invoice form rejects an amount that is not a positive number and shows a validation message.
- The generated invoice can be downloaded as a PDF document.
FR-02 The application lists all invoices created by the signed-in user, newest first.
""" + ("Additional background text about invoicing. " * 10)


def _req(**kw):
    base = {"title": "Create invoice", "description": "The user can create an invoice", "priority": "high",
            "kind": "functional", "verifiability": "both",
            "source_quote": "The user can create an invoice by entering the customer name, the amount and the due date.",
            "acceptance_criteria": [
                {"statement": "The invoice form rejects an amount that is not a positive number", "oracle_hint": "deterministic"},
                {"statement": "Invoices are synchronised to SAP every night within 5 minutes", "oracle_hint": "deterministic",
                 "verifiability": "runtime"},
            ]}
    base.update(kw)
    return base


def test_criteria_grounding_and_verifiability():
    reqs, dropped = normalize_requirements([_req()], BrdIndex(BRD), brd_source="repository")
    assert dropped == 0
    c1, c2 = reqs[0]["criteria"]
    assert c1["grounded"] is True and c1["verifiability"] == "both" and c1["confidence"] == 1.0
    assert c2["grounded"] is False and c2["verifiability"] == "runtime" and c2["confidence"] < 1.0
    assert reqs[0]["self_generated"] is False and reqs[0]["origin"] == "brd"


def test_generated_brd_is_self_generated_and_capped():
    reqs, _ = normalize_requirements([_req()], BrdIndex(BRD), brd_source="generated_live")
    r = reqs[0]
    assert r["self_generated"] is True and r["origin"] == "inferred" and r["confidence"] <= 0.6
    assert all(c["self_generated"] and c["confidence"] <= 0.6 for c in r["criteria"])
    code, _ = normalize_requirements([_req()], BrdIndex(BRD), brd_source="generated")
    assert code[0]["origin"] == "descriptive" and code[0]["self_generated"] is True


def test_caps_become_limitations():
    many_criteria = _req(acceptance_criteria=[{"statement": f"The invoice form rejects an amount case {i}",
                                               "oracle_hint": "semantic"} for i in range(11)])
    limitations = []
    reqs, _ = normalize_requirements([many_criteria] * (brd_agent.MAX_REQUIREMENTS + 3), BrdIndex(BRD),
                                     limitations=limitations)
    assert len(reqs) == brd_agent.MAX_REQUIREMENTS
    assert len(reqs[0]["criteria"]) == brd_agent.MAX_CRITERIA
    text = " ".join(limitations)
    assert "3 beyond" in text and f"first {brd_agent.MAX_CRITERIA} acceptance criteria" in text


def test_long_brd_is_cut_with_limitation(tmp_path):
    p = tmp_path / "BRD.md"
    p.write_text("Requirement text. " * 10_000, encoding="utf-8")
    limitations = []
    text, method = brd_source.read_brd(p, llm=None, limitations=limitations)
    assert len(text) == brd_source.MAX_BRD_CHARS and method == "text"
    assert limitations and "only the first" in limitations[0]


PROFILE = {
    "app_type": "Document Generator", "forms": 1, "downloads": True, "chat_interface": False, "authentication": True,
    "live_url": "https://app.example.com", "pages_inspected": 2, "classification_signals": ["1 multi-field form"],
    "user_flows": [{"name": "Submit form on /new", "steps": ["Open /new", "Fill 3 field(s)", "Click 'Generate'"]}],
    "api_calls": [{"method": "POST", "path": "/api/invoices", "status": 200}],
    "pages": [
        {"url": "https://app.example.com/login", "path": "/login", "title": "Sign in", "headings": [], "buttons": ["Sign in"],
         "forms": [{"is_login": True, "fields": [{"label": "Password", "type": "password"}]}], "downloads": {}},
        {"url": "https://app.example.com/new", "path": "/new", "title": "New invoice", "headings": ["Create invoice"],
         "buttons": ["Generate", "Download PDF"], "downloads": {"buttons": ["Download PDF"], "links": []},
         "forms": [{"is_login": False, "field_count": 3, "submit_button": "Generate", "fields": [
             {"label": "Customer name", "type": "text", "required": True},
             {"label": "Amount", "type": "number", "required": True},
             {"label": "Currency", "type": "select", "options": ["EUR", "USD"]}]}]},
    ],
}


def test_evidence_from_runtime_profile():
    ev = live_discovery.evidence_from_runtime_profile(PROFILE)
    text = live_discovery.render_evidence(ev)
    assert [e["kind"] for e in ev] == ["app_profile", "page", "page", "api_calls"]
    assert "Customer name (text, required)" in text and "options: EUR, USD" in text and "Download PDF" in text
    assert "POST /api/invoices" in text
    assert live_discovery.evidence_from_runtime_profile({"app_type": "Behind login", "pages": PROFILE["pages"][:1]}) == []
    assert live_discovery.evidence_from_runtime_profile(None) == []


def test_agent_answers_are_claims(monkeypatch):
    monkeypatch.setattr(live_discovery, "_get", lambda *a, **k: None)

    class Chat:
        def send(self, q):
            return type("R", (), {"ok": True, "text": "I can do everything, including payroll."})()

    ev = live_discovery.collect_live_evidence("https://agent.example.com", lambda m: None, chat=Chat())
    assert ev and all(e["kind"] == "agent_claim" and "CLAIM" in e["source"] for e in ev)


class FakeLLM:
    def __init__(self, fail_selection=False):
        self.prompts = []
        self.fail_selection = fail_selection

    def generate(self, prompt):
        raise AssertionError("generate_json expected")

    def generate_json(self, prompt, schema=None, temperature=None):
        self.prompts.append(prompt)
        if schema is BRD_SELECTION:
            if self.fail_selection:
                raise RuntimeError("503 UNAVAILABLE")
            return json.dumps({"selected_path": "docs/b.md", "reason": "names the invoice builder"})
        if schema is BRD_DOCUMENT:
            return json.dumps({"brd_markdown": BRD})
        if schema is REQUIREMENTS:
            return json.dumps({"requirements": [_req()]})
        raise AssertionError(schema)


def _agent(llm):
    agent = BrdBuilderAgent({})
    agent._registry.get_llm = lambda *a, **k: llm
    return agent


def test_live_only_uses_runtime_profile_without_crawling(tmp_path, monkeypatch):
    def no_crawl(*a, **k):
        raise AssertionError("must not crawl when runtime_profile is present")

    monkeypatch.setattr(brd_agent, "collect_live_evidence", no_crawl)
    monkeypatch.setattr(brd_agent, "connect_live_agent", no_crawl)
    llm = FakeLLM()
    out = _agent(llm).execute({"mode": "live_only", "repo_dir": str(tmp_path), "live_url": "https://app.example.com",
                               "runtime_profile": PROFILE, "agent_profile": {}, "code_digest": ""}, {})
    assert out["status"] == "success" and out["brd_source"] == "generated_live"
    assert "Customer name" in llm.prompts[0] and '<untrusted_content source="live_app_evidence">' in llm.prompts[0]
    assert all(r["self_generated"] and r["confidence"] <= 0.6 for r in out["requirements"])
    assert any("generated by MTA" in x for x in out["limitations"])
    assert out["ungrounded_criteria"] == ["AC-01.2"]


def _docs(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# Other product TSD\n" + "Unrelated technical spec. " * 400, encoding="utf-8")
    (tmp_path / "docs" / "b.md").write_text(BRD, encoding="utf-8")
    return ["docs/a.md", "docs/b.md"]


def test_auto_detect_reads_previews_then_full_choice(tmp_path):
    cands = _docs(tmp_path)
    llm = FakeLLM()
    out = _agent(llm).execute({"mode": "brd_and_live", "repo_dir": str(tmp_path), "brd_candidates": cands,
                               "agent_profile": {"purpose": "invoices"}, "code_digest": ""}, {})
    assert out["status"] == "success" and out["brd_path"] == "docs/b.md"
    selection_prompt = llm.prompts[0]
    assert "Unrelated technical spec." * 1 in selection_prompt
    assert len(selection_prompt) < 2 * brd_source.PREVIEW_CHARS + 6000  # previews, not whole documents


def test_selector_failure_is_reported(tmp_path):
    cands = _docs(tmp_path)
    warnings = []
    out = _agent(FakeLLM(fail_selection=True)).execute(
        {"mode": "brd_and_live", "repo_dir": str(tmp_path), "brd_candidates": cands, "agent_profile": {},
         "code_digest": "", "emit": lambda m, level="info": warnings.append((level, m))}, {})
    # the unconfirmed first candidate (a TSD) is used, its requirements don't trace — but the user is told why
    assert any("docs/a.md, WITHOUT confirming" in x for x in out["limitations"])
    assert any(level == "warning" and "WITHOUT confirming" in m for level, m in warnings)
