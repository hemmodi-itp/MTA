"""Phase 3.2 — decision-table collapse and pairwise coverage (exact cases + hypothesis properties)."""

import itertools

from hypothesis import given, settings, strategies as st

from tools.test_design.decision_table import DC, build, collapse, covers
from tools.test_design.pairwise import all_pairs, covered_pairs

DISCOUNT = [
    {"when": {"valid_code": True, "already_applied": False}, "then": "10% off"},
    {"when": {"valid_code": True, "already_applied": True}, "then": "Discount already applied"},
    {"when": {"valid_code": False}, "then": "Invalid discount code"},
]


# ── decision tables ───────────────────────────────────────────────────────────

def test_build_maps_every_combination_to_first_matching_rule():
    cols = build(["valid_code", "already_applied"], DISCOUNT)
    assert cols == [((True, True), "Discount already applied"), ((True, False), "10% off"),
                    ((False, True), "Invalid discount code"), ((False, False), "Invalid discount code")]


def test_collapse_merges_dont_care_condition():
    full = build(["valid_code", "already_applied"], DISCOUNT)
    assert collapse(full) == [((True, True), "Discount already applied"), ((True, False), "10% off"),
                              ((False, DC), "Invalid discount code")]
    assert covers(collapse(full), full)


def test_collapse_three_conditions_to_two_rules():
    rules = [{"when": {"signed_in": True, "admin": True}, "then": "admin page"},
             {"when": {"signed_in": True, "admin": False}, "then": "403"},
             {"when": {"signed_in": False}, "then": "login redirect"}]
    full = build(["signed_in", "admin", "beta"], rules)          # 'beta' never matters
    c = collapse(full)
    assert c == [((True, True, DC), "admin page"), ((True, False, DC), "403"), ((False, DC, DC), "login redirect")]
    assert covers(c, full)


def test_unspecified_combinations_are_none_and_not_merged_with_actions():
    full = build(["a", "b"], [{"when": {"a": True, "b": True}, "then": "x"}])
    assert [a for _, a in full].count(None) == 3
    assert collapse([c for c in full if c[1] is not None]) == [((True, True), "x")]


@settings(max_examples=120, deadline=None)
@given(n=st.integers(2, 5), data=st.data())
def test_collapse_preserves_every_action_and_is_deterministic(n, data):
    actions = data.draw(st.lists(st.sampled_from(["A", "B", "C"]), min_size=2 ** n, max_size=2 ** n))
    full = list(zip(itertools.product((True, False), repeat=n), actions))
    c1, c2 = collapse(full), collapse(list(reversed(full)))
    assert c1 == c2                                   # independent of input order
    assert covers(c1, full)                           # every original column → exactly one, same action
    assert len(c1) <= len(full)


# ── pairwise ──────────────────────────────────────────────────────────────────

FILTERS = [("q", ["", "e"]), ("category", ["All", "Books", "Electronics", "Home"]),
           ("sort", ["Default", "Price asc", "Price desc", "Name"])]


def test_every_pair_present_for_search_filters():
    rows = all_pairs(FILTERS)
    assert covered_pairs(rows, FILTERS)
    assert len(rows) == 16                            # 4×4 lower bound (category × sort)
    assert rows == all_pairs(FILTERS)                 # deterministic


def test_pairwise_is_smaller_than_the_full_product():
    params = [(f"p{i}", [0, 1, 2]) for i in range(5)]
    rows = all_pairs(params)
    assert covered_pairs(rows, params)
    assert len(rows) < 3 ** 5 and len(rows) <= 15


def test_degenerate_inputs():
    assert all_pairs([]) == []
    assert all_pairs([("a", [1, 2])]) == [{"a": 1}, {"a": 2}]
    assert all_pairs([("a", [1]), ("b", [])]) == []


@settings(max_examples=80, deadline=None)
@given(sizes=st.lists(st.integers(1, 5), min_size=2, max_size=6))
def test_pairwise_property_every_pair_covered(sizes):
    params = [(f"p{i}", list(range(s))) for i, s in enumerate(sizes)]
    rows = all_pairs(params)
    assert covered_pairs(rows, params)
    assert all(set(r) == {n for n, _ in params} for r in rows)
    biggest = sorted(sizes)[-2:]
    assert len(rows) >= biggest[0] * biggest[1]       # can't beat the two largest parameters' product
