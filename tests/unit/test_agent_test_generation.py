"""Unit tests for AgentTestGenerationAgent's guarantees: every kept test is executable, none repeats another, the
families keep their budget shares, and a runtime criterion left without a test gets a targeted top-up — no LLM."""

import json

import agents.test_creation.agent_test_generation.agent as gen
from agents.test_creation.agent_test_generation.agent import normalize_tests

BRD = ("## Features\nThe system shall generate all five deliverables from the structured form.\n"
       "Users can submit a free-text change request to revise a run.\n"
       "Failures of individual agents are captured and retried automatically.\n")
REQS = [
    {"code": "REQ-01", "title": "Generate", "priority": "medium", "verifiability": "both",
     "criteria": [{"code": "AC-01.1", "statement": "All five deliverables are generated from the form"}]},
    {"code": "REQ-06", "title": "Revise", "priority": "medium", "verifiability": "both",
     "criteria": [{"code": "AC-06.1", "statement": "A free-text change request revises the run"}]},
    {"code": "REQ-11", "title": "Retry", "priority": "medium", "verifiability": "both",
     "criteria": [{"code": "AC-11.1", "statement": "Agent failures are captured and retried"}]},
]
QUOTES = {"REQ-01": "The system shall generate all five deliverables from the structured form.",
          "REQ-06": "Users can submit a free-text change request to revise a run.",
          "REQ-11": "Failures of individual agents are captured and retried automatically."}


def _t(ref, crit, title, family="agent_specific", variant="positive", inp="Project Name: Clinic\nProblem Statement: x",
       expected="It works"):
    return {"title": title, "category": family, "variant_type": variant, "requirement_ref": ref, "criterion_code": crit,
            "brd_reference": QUOTES[ref], "input": inp, "expected_behavior": expected}


def test_the_general_family_cannot_repeat_agent_specific_positives_or_exceed_its_share():
    raw = [_t("REQ-01", "AC-01.1", "Generate full document set from the form"),
           _t("REQ-06", "AC-06.1", "Submit a change request"),
           # run cmvc4qzw: the general family re-generated every agent-specific positive test
           _t("REQ-01", "AC-01.1", "Generate all five deliverables from structured form input", family="general"),
           _t("REQ-06", "AC-06.1", "Submit free-text change request on existing run", family="general"),
           _t("REQ-01", "AC-01.1", "Empty form is refused", family="general", variant="negative", expected="An error names the fields"),
           _t("REQ-01", "AC-01.1", "Empty form is refused again", family="general", variant="negative", expected="An error names the fields"),
           _t("REQ-06", "AC-06.1", "Blank change request is refused", family="general", variant="negative", expected="Refused")]
    tests, dropped = normalize_tests(raw, REQS, BRD, allowed_criteria={"AC-01.1", "AC-06.1"}, family_caps={"general": 1})
    assert [(t["category"], t["variant_type"], t["criterion_code"]) for t in tests] == [
        ("agent_specific", "positive", "AC-01.1"), ("agent_specific", "positive", "AC-06.1"),
        ("general", "negative", "AC-01.1")]
    assert dropped["repeats another test of the same criterion"] == 3      # 2 positives + 1 near-identical negative
    assert dropped["over its family's share of the budget"] == 1


def test_a_test_that_needs_a_fault_injected_is_kept_and_run():
    # every generated test runs: Action Generation runs it as an ordinary use of the feature (a "proxy")
    raw = [_t("REQ-11", "AC-11.1", "LLM generation failure capture and retry", family="general", variant="robustness",
              inp="Scenario: Submit document generation request during transient LLM API rate-limit or timeout event.")]
    tests, dropped = normalize_tests(raw, REQS, BRD)
    assert [t["criterion_code"] for t in tests] == ["AC-11.1"] and not any(dropped.values())


def test_literal_backslash_n_inputs_are_unescaped():
    raw = [_t("REQ-01", "AC-01.1", "Generate", inp="Scenario: x\\nProject Name: Clinic\\nProblem Statement: y")]
    tests, _ = normalize_tests(raw, REQS, BRD)
    assert tests[0]["input"].splitlines() == ["Scenario: x", "Project Name: Clinic", "Problem Statement: y"]


class _LLM:
    pass


def test_a_runtime_criterion_left_without_a_test_gets_a_top_up(monkeypatch):
    prompts = []

    def fake_generate_json(llm, prompt, required_keys=None, schema=None, **kw):
        prompts.append(prompt)
        if "exactly one positive test" in prompt:                          # the top-up call
            return {"test_cases": [_t("REQ-06", "AC-06.1", "Revise the generated run")]}
        if "General tests" in prompt:
            return {"test_cases": [_t("REQ-01", "AC-01.1", "Generate again", family="general")]}
        return {"test_cases": [_t("REQ-01", "AC-01.1", "Generate"),
                               _t("REQ-11", "AC-11.1", "Retry on LLM failure",
                                  inp="Scenario: simulate an LLM API failure during generation")]}

    monkeypatch.setattr(gen, "generate_json", fake_generate_json)
    agent = gen.AgentTestGenerationAgent({})
    monkeypatch.setattr(agent._registry, "get_llm", lambda *a, **k: _LLM())
    profile = {"app_type": "Document Generator", "pages_inspected": 1, "login": {"succeeded": True}, "pages": [
        {"path": "/new", "forms": [{"fields": [{"label": "Project Name (required)", "type": "text", "required": True}],
                                    "submit_button": "Generate", "buttons": ["Generate"]}], "buttons": ["Generate"]}]}
    out = agent.execute({"requirements": REQS, "brd_markdown": BRD, "mode": "brd_and_live", "live_url": "https://app.example",
                         "runtime_profile": profile, "app_classification": {"app_type": "Document Generator"}}, {})
    by = {t["criterion_code"]: t for t in out["test_cases"]}
    assert set(by) == {"AC-01.1", "AC-06.1", "AC-11.1"} and by["AC-06.1"]["title"] == "Revise the generated run"
    assert sum(1 for p in prompts if "exactly one positive test" in p) == 1
    assert "AC-11.1" not in json.dumps([p for p in prompts if "exactly one positive test" in p])  # it has its test
    assert not out["static_only_criteria"]                                    # every runtime criterion has a test
