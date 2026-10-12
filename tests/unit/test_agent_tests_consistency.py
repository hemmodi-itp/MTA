"""Consistency scorer (tools/agent_tests/checks/consistency.py, design D8)."""

import pytest

from tools.agent_tests.checks.consistency import key_facts, score, similarity

pytestmark = pytest.mark.mta

RIGHT = "We're open 9am to 6pm, Monday to Saturday. We're closed on Sundays. (Source: Store hours)"
WRONG = "We're open 10am to 8pm, seven days a week. (Source: Store hours)"


def test_identical_replies_pass():
    r = score([RIGHT] * 5, 0.8)
    assert r.result == "pass" and r.min_similarity == 1.0


def test_fact_disagreement_fails_even_when_wording_is_close():
    r = score([RIGHT, RIGHT, WRONG, RIGHT, WRONG], 0.8)
    assert r.result == "fail" and "disagree on key facts" in r.detail and "time:9:00am" in r.detail


def test_paraphrase_with_same_facts_is_unsure_not_fail():
    a = "Returns are accepted within 30 days if you have a receipt."
    b = "Bring your receipt and you can send it back up to 30 days after buying."
    r = score([a, b], 0.8)
    assert r.result == "unsure" and "wording similarity" in r.detail


def test_key_facts():
    assert key_facts(RIGHT) >= {"time:9:00am", "time:6:00pm", "day:monday", "day:saturday", "day:sunday"}
    assert key_facts("Free over $50, 3 to 5 business days") == {"num:50", "num:3", "num:5"}
    assert "yn:yes" in key_facts("Yes, we do.")
    assert key_facts("I'm sorry, I don't know that.") == frozenset()


def test_similarity_bounds_and_edge_cases():
    assert similarity("a b c", "a b c") == 1.0
    assert similarity("", "") == 1.0
    assert 0.0 <= similarity("open today", "closed tomorrow") < 0.5
    assert score(["only one"], 0.8).result == "unsure"
