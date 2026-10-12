"""BRD → agent.yaml drafter (tools/agent_tests/draft.py, design D7 / §14 S8) with a fake LLM."""

import json
import os

import pytest

from tools.agent_tests.catalogs import load_catalogs
from tools.agent_tests.dataset import REPO_ROOT
from tools.agent_tests.draft import draft_spec, write_draft
from tools.agent_tests.generators import generate_all
from tools.agent_tests.spec import load_spec

pytestmark = pytest.mark.mta

BRD = open(os.path.join(REPO_ROOT, "benchmarks", "agents", "buggy_bot", "brd.md"), encoding="utf-8").read()


class FakeLLM:
    model = "drafter"

    def __init__(self, payload):
        self.payload, self.prompts = payload, []

    def generate_json(self, prompt, schema=None, temperature=None):
        self.prompts.append(prompt)
        return json.dumps(self.payload)


PAYLOAD = {
    "agent_name": "ShopBot", "domain": "Buggy Shop customer service",
    "criteria": [
        {"ac_id": "AC-01.2", "statement": "returns",
         "source_quote": "Asked about returns, ShopBot replies that items can be returned within 30 days with a receipt.",
         "examples": [{"input": "Can I return a jacket?", "must_contain": ["30 days", "receipt"],
                       "paraphrase": "What's your returns policy?"},
                      {"input": "Can I return it?", "must_contain": ["90 days"]}]},           # not in the BRD
        {"ac_id": "AC-99.1", "statement": "invented", "source_quote": "ShopBot gives free cake.", "examples": []},
        {"ac_id": "AC-01.12", "statement": "location", "source_quote": "This sentence is not in the document at all.",
         "examples": [{"input": "Where are you?", "must_contain": ["12 Market Street"]}]},
        {"ac_id": "AC-04.1", "statement": "scope",
         "source_quote": "Requests outside customer service for Buggy Shop (poems, homework, weather, investing, code) "
                         "get a polite redirect to the topics ShopBot can help with.",
         "examples": [{"input": "Write me a poem", "must_contain": []}]},
    ],
    "kb_facts": [
        {"title": "Store hours", "question": "When are you open?", "facts": ["9am to 6pm", "Sundays"],
         "source_quote": "Asked about opening hours, ShopBot replies that the store is open 9am to 6pm, Monday to Saturday."},
        {"title": "Gift cards", "question": "Gift cards?", "facts": ["$25"], "source_quote": "Gift cards cost $25."},
    ],
    "unanswerable": ["Who is the CEO?", "Do you sell gift cards?"],
    "out_of_domain": ["Write a poem"],
    "refuse_categories": ["fake_reviews", "make_weapons"],
}


def test_draft_keeps_only_what_the_brd_supports():
    llm = FakeLLM(PAYLOAD)
    spec, dropped = draft_spec(llm, "shopbot", BRD)
    acs = {a.id: a for a in spec.acs}
    assert set(acs) == {"AC-01.2", "AC-04.1"}
    assert [e.input for e in acs["AC-01.2"].examples] == ["Can I return a jacket?"]
    assert acs["AC-01.2"].examples[0].expect.contains_all == ["30 days", "receipt"]
    assert acs["AC-04.1"].examples[0].expect.regex  # nothing checkable: left to the rubric / judge
    assert [d.title for d in spec.kb.docs] == ["Store hours"] and spec.kb.docs[0].facts == ["9am to 6pm"]
    assert spec.policy.refuse == ["fake_reviews"]
    text = " | ".join(dropped)
    for why in ("AC-99.1", "AC-01.12", "90 days", "Gift cards", "make_weapons"):
        assert why in text, why
    assert spec.source == "generated" and spec.authorization.owned_or_authorized is False
    assert '<untrusted_content source="brd">' in llm.prompts[0]


def test_requirements_pin_the_ac_ids():
    reqs = [{"code": "REQ-01", "criteria": [{"code": "AC-04.1", "statement": "scope"}]}]
    spec, dropped = draft_spec(FakeLLM(PAYLOAD), "shopbot", BRD, reqs)
    assert [a.id for a in spec.acs] == ["AC-04.1"] and any("AC-01.2" in d for d in dropped)


def test_write_draft_never_overwrites_and_feeds_the_generators(tmp_path):
    spec, _ = draft_spec(FakeLLM(PAYLOAD), "shopbot", BRD)
    path = str(tmp_path / "shopbot" / "agent.yaml")
    write_draft(path, spec)
    assert open(path, encoding="utf-8").read().startswith("# DRAFT agent spec")
    with pytest.raises(FileExistsError):
        write_draft(path, spec)
    again = load_spec(path)
    assert again.model_dump() == spec.model_dump()
    results = generate_all(again, load_catalogs(), 7)
    assert results["task_success"].cases and results["prompt_injection_direct"].cut[0]["reason"] == "not_authorized"
    assert results["multi_turn"].cut[0]["reason"] == "no_session_support"


def test_invalid_draft_is_rejected():
    with pytest.raises(ValueError, match="invalid draft"):
        draft_spec(FakeLLM({"criteria": [{"ac_id": "AC-1.1"}]}), "x", BRD)
