"""Phase 1.1 — quote-verifier tests: exact, near-exact (transcription), paraphrased and fabricated quotes.

The verifier is the Agent-Eval BrdIndex, moved into tools/requirements/brd_index.py and re-exported from
tools/agent_eval/brd_source.py (one implementation for both pipelines)."""

import pytest

from tools.requirements.brd_index import BrdIndex

BRD = """### REQ-03 Product management
- AC-03.2: Name must be 1–50 characters; a name of exactly 50 characters is accepted and 51 or more is
  rejected with "Name must be at most 50 characters".
- AC-04.2: Any other file type (for example `.exe`, `.txt`, `.pdf`) is rejected by the server with
  "Only CSV or PNG files are allowed"; files over 1 MB are rejected with "File must be 1 MB or smaller".
Signed-in users can add, edit and delete products. Valida-
tion runs in the browser and is always enforced again on the server.
"""


@pytest.fixture(scope="module")
def index():
    return BrdIndex(BRD)


@pytest.mark.parametrize("quote", [
    "a name of exactly 50 characters is accepted",
    'rejected with "Name must be at most 50 characters"',
    "A NAME OF EXACTLY 50 CHARACTERS IS ACCEPTED",                    # case
    "a name   of exactly 50\ncharacters is accepted",                  # whitespace / line breaks
    "**Signed-in users** can add, edit and delete products",           # markdown noise
    "Validation runs in the browser",                                  # PDF hyphenation "Valida-\ntion"
])
def test_exact_quotes(index, quote):
    assert index.quote_match(quote) == "exact"
    assert index.grounded(quote)


@pytest.mark.parametrize("quote", [
    "files over 1 MB are rejected with File must be 1MB or smaller",   # small transcription difference
    "Validation runs in the browser and is always enforced again on server",   # one word dropped
])
def test_near_exact_quotes_are_fuzzy(index, quote):
    assert index.quote_match(quote) == "fuzzy"


@pytest.mark.parametrize("quote", [
    "Product names may contain at most fifty characters",               # paraphrase
    "The upload refuses executables and documents bigger than a megabyte",
])
def test_paraphrased_quotes_are_not_verified(index, quote):
    assert index.quote_match(quote) == "none"
    assert not index.grounded(quote)


def test_paraphrase_still_has_measurable_support(index):
    # A restated criterion is not a quote, but its words come from the document (recorded as `support`).
    assert index.support("A name of 51 characters is rejected") >= 0.7


@pytest.mark.parametrize("quote", [
    "Passwords must contain a special character and expire every 90 days",
    "The admin can export all orders to Excel",
    "Two-factor authentication is mandatory for administrators",
])
def test_fabricated_quotes_are_rejected(index, quote):
    assert index.quote_match(quote) == "none"
    assert index.support(quote) < 0.7


@pytest.mark.parametrize("quote", ["", None, "accepted", "Name must"])
def test_too_short_or_empty(index, quote):
    assert index.quote_match(quote) == "none"


def test_agent_eval_reexport_is_the_same_implementation():
    from tools.agent_eval.brd_source import BrdIndex as AgentEvalBrdIndex
    from tools.agent_eval.brd_source import CRITERION_SUPPORT

    assert AgentEvalBrdIndex is BrdIndex
    assert CRITERION_SUPPORT == 0.7
