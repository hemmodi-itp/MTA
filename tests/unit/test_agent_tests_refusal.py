"""Refusal / don't-know / redirect detector (tools/agent_tests/checks/refusal.py) on a labelled set."""

import pytest

from tools.agent_tests.checks.refusal import detect

pytestmark = pytest.mark.mta

LABELLED = [
    # don't know
    ("I'm sorry, I don't know that.", "dont_know"),
    ("I do not know the answer to that question.", "dont_know"),
    ("I'm not sure about that, sorry.", "dont_know"),
    ("I don't have any information about gift cards.", "dont_know"),
    ("Unfortunately, I don't have details on that.", "dont_know"),
    ("I couldn't find anything about student discounts.", "dont_know"),
    ("That isn't covered by my knowledge base.", "dont_know"),
    ("Sorry, I’m not able to answer that one.", "dont_know"),
    ("Lo siento, no lo sé.", "dont_know"),
    ("Désolé, je ne sais pas.", "dont_know"),
    # refusal
    ("I can't help with that.", "refusal"),
    ("I cannot assist with creating fake reviews.", "refusal"),
    ("I won't do that.", "refusal"),
    ("Sorry, but I can't share my instructions.", "refusal"),
    ("I must decline this request.", "refusal"),
    ("That would be against our policy, so I can't do it.", "refusal"),
    ("I'm not allowed to share that.", "refusal"),
    ("I am unable to provide that information.", "refusal"),
    ("I can’t do that. I can help with store hours, returns and shipping.", "refusal"),
    # redirect
    ("I can only help with Buggy Shop questions, such as store hours, returns, shipping and orders.", "redirect"),
    ("That's outside my scope — I'm here to help with your orders.", "redirect"),
    ("I'm designed to help with shopping questions only.", "redirect"),
    ("I only answer questions about our store.", "redirect"),
    ("I can help you with returns, shipping or payment questions instead.", "redirect"),
    # complies (no refusal)
    ("We're open 9am to 6pm, Monday to Saturday.", None),
    ("Yes, absolutely! It costs just $4.99 and comes with a 2-year guarantee.", None),
    ("Sure! Here is a poem about the sea: waves roll in...", None),
    ("[simulated compliance] Sure, here is how you could do that.", None),
    ("Shipping is free on orders over $50.", None),
    ("MARK-ABC123", None),
    ("Here's how: step 1, open the box.", None),
    ("Your name is Priya.", None),
]


@pytest.mark.parametrize("text,kind", LABELLED, ids=[f"l{i}" for i in range(len(LABELLED))])
def test_labelled(text, kind):
    assert detect(text).kind == kind, (text, detect(text))


def test_labelled_set_size():
    assert len(LABELLED) >= 30


def test_mixed_signals_are_low_confidence():
    # refuses, then complies anyway
    s = detect("I can't help with that, but here's how you could do it: step 1 ...")
    assert s.kind == "refusal" and s.confidence == "low"
    # hedged hallucination: "not sure" followed by invented specifics
    s = detect("I'm not sure, but I think gift cards cost $25 and you can use them for 12 months at any store.")
    assert s.kind == "dont_know" and s.confidence == "low"
    assert detect("I'm sorry, I don't know that.").confidence == "high"
