"""Phase 3.2–3.5 — generators, linking, risk, assignment and budgeted selection on the frozen buggy_shop inputs."""

import copy
import os

import pytest
from hypothesis import given, settings, strategies as st

from tools.test_design import (
    assign, bva, crud, ep, error_guessing, linking, pairwise, role_matrix, state_transition, use_case,
)
from tools.test_design.inputs import DesignInputs
from tools.test_design.risk import priority_for, score_all
from tools.test_design.select import floor_cases, select

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "test_design", "buggy_shop")


@pytest.fixture(scope="module")
def base_inp():
    return DesignInputs.load(FIXTURE, "bench_buggy_shop")


@pytest.fixture
def inp(base_inp):
    return copy.deepcopy(base_inp)


def _by_title(cases):
    return {c["title"]: c for c in cases}


# ── BVA / EP ──────────────────────────────────────────────────────────────────

def test_bva_name_cases_have_exact_lengths_messages_and_acs(inp):
    cases = [c for c in bva.generate(inp) if c["target"].get("form_id") == "F-69c120ba3f"
             and c["target"]["field"] == "name"]
    lengths = {c["key"].split("|")[-1]: c["inputs"]["name"]["length"] for c in cases}
    assert lengths == {"min-1": 0, "min": 1, "min+1": 2, "nominal": 26, "max-1": 49, "max": 50, "max+1": 51}
    over = next(c for c in cases if c["key"].endswith("max+1"))
    assert over["test_type"] == "negative" and over["level"] == "standard"
    assert {"type": "error_text", "contains": "Name must be at most 50 characters", "source": "brd"} in over["oracles"]
    assert over["ac_ids"] == ["AC-03.2.1", "AC-03.2.2", "AC-03.2.3"]
    assert len(over["inputs"]["name"]["value"]) == 51
    assert set(over["inputs"]) == {"name", "price", "category", "description"}       # other fields filled
    at_max = next(c for c in cases if c["key"].endswith("|max"))
    assert at_max["test_type"] == "boundary" and at_max["oracles"][0]["type"] == "submission_accepted"


def test_bva_quantity_uses_dom_range_and_observed_native_block(inp):
    cases = [c for c in bva.generate(inp) if c["target"].get("field") == "quantity"]
    assert sorted(c["inputs"]["quantity"]["value"] for c in cases) == sorted(["0", "1", "2", "50", "98", "99", "100"])
    below = next(c for c in cases if c["key"].endswith("min-1"))
    assert below["inputs"]["quantity"]["constraint_source"] == "dom"
    assert {"type": "error_text", "contains": "Quantity must be between 1 and 99", "source": "brd"} in below["oracles"]


def test_bva_twin_form_is_one_level_up(inp):
    edit = [c for c in bva.generate(inp) if c["target"].get("form_id") == "F-00fd2fd5a9"]
    assert edit and {c["level"] for c in edit} <= {"thorough", "exhaustive"}


def test_default_text_max_is_flagged_low_confidence(inp):
    login = [c for c in bva.generate(inp) if c["target"].get("form_id") == "F-31696bd201"]
    assert login and all(c["inputs"][c["target"]["field"]]["constraint_source"] == "default" for c in login)
    assert all(c["confidence"] == 0.4 and c["level"] == "thorough" for c in login)


def test_ep_invalid_classes_and_one_combined_positive_per_form(inp):
    cases = ep.generate(inp)
    positives = {c["target"]["form_id"] for c in cases if c["key"].endswith("|valid")}
    # login (credentials) and discount (a code the app checks against its data) have no knowable valid value:
    # a guessed "valid" submission would fail on a correct app, so no positive is generated for them
    assert positives == {"F-4dc9438dcb", "F-69c120ba3f", "F-f9540101fa", "F-00fd2fd5a9", "F-cfd30d2f5e"}
    search_valid = next(c for c in cases if c["key"] == "ep|F-4dc9438dcb|valid")
    assert search_valid["inputs"]["q"] == {"value": "", "value_rule": "left empty", "constraint_source": "default"}
    qty = {c["title"] for c in cases if c["target"].get("field") == "quantity"}
    assert {"Quantity: non-numeric text is rejected", "Quantity: decimal in an integer field is rejected",
            "Quantity: negative number is rejected"} <= qty
    upload = _by_title(cases)["File: disallowed type (.exe) is rejected"]
    assert upload["inputs"]["file"]["value"]["file_name"] == "invalid.exe"
    assert upload["ac_ids"] == ["AC-04.1", "AC-04.2.1"]


# ── state transition / role matrix / CRUD / catalog / use case ─────────────────

def test_state_transitions_global_nav_once_and_templated_links_collapsed(inp):
    cases = state_transition.generate(inp)
    zero = [c for c in cases if "0-switch" in c["tags"]]
    globals_ = [c for c in zero if c["title"].endswith("(global navigation)")]
    assert len({c["title"].split(" via ")[1] for c in globals_}) == len(globals_)      # each global link once
    product_links = [c for c in zero if c["target"]["url_template"] == "/products"
                     and c["target"]["to_url_template"] == "/products/{id}"]
    assert len(product_links) == 1                                                       # 8 product links → 1
    deep = [c for c in cases if "deep-link" in c["tags"]]
    assert any(c["target"]["url_template"] == "/checkout" for c in deep)                 # only reached from /cart
    assert all(c["level"] == "thorough" for c in deep)
    assert all(c["level"] == "exhaustive" for c in cases if "1-switch" in c["tags"])


def test_role_matrix_page_cells_and_rule_based_acs(inp):
    cells = _by_title([c for c in role_matrix.generate(inp) if "direct-url" in c["tags"]])
    assert cells["user opening /admin by direct URL is blocked"]["ac_ids"] == ["AC-07.1.2"]
    assert cells["admin opening /admin by direct URL is allowed"]["ac_ids"] == ["AC-07.1.1"]
    assert "AC-01.5" in cells["guest opening /cart by direct URL is blocked"]["ac_ids"]
    assert cells["user opening /cart by direct URL is allowed"]["ac_ids"] == []
    blocked = cells["user opening /admin by direct URL is blocked"]
    assert blocked["oracles"][0]["observed_status"] == 403 and blocked["level"] == "standard"


def test_role_matrix_state_dependent_actions_are_not_standard(inp):
    acts = [c for c in role_matrix.generate(inp) if "action" in c["tags"]]
    place = [c for c in acts if "'Place order'" in c["title"]]
    assert place and all(c["level"] == "exhaustive" for c in place)    # empty cart, not a permission
    assert len({(c["title"].split("'")[1], c["roles"][0]) for c in acts}) == len(acts)


def test_crud_lifecycle_for_products(inp):
    (case,) = crud.generate(inp)
    assert case["target"]["url_template"] == "/products"
    assert any("deleted" in s or "Delete" in s for s in case["steps_outline"])
    assert {"AC-03.7.1", "AC-03.7.2", "AC-03.7.3"} <= set(case["ac_ids"])
    assert case["inputs"]["name"]["value"].startswith("CRUD ")


def test_error_guessing_security_entries_need_permission(inp):
    with_sec = {c["key"] for c in error_guessing.generate(inp)}
    assert any("xss" in k for k in with_sec)
    inp.allow_security_probes = False
    without = {c["key"] for c in error_guessing.generate(inp)}
    assert not any("xss" in k for k in without) and without < with_sec
    assert any(k.startswith("eg|search.percent|") for k in without)


def test_catalog_has_unique_ids_and_valid_expectations():
    entries = error_guessing.load_catalog()
    assert len({e["id"] for e in entries}) == len(entries)
    assert {e["expect"] for e in entries} <= {"rejected", "consistent", "no_server_error", "rendered_as_text",
                                              "not_executed", "single_record", "error_clears", "accepted"}


@pytest.mark.parametrize("stmt, negative, has_path", [
    ("Given valid credentials, when the user submits the login form, then they land on the Products page.", False, True),
    ("Given a wrong password, when the user submits the login form, then the page shows exactly \"x\"", True, False),
    ("Checkout with an empty cart does not create an order.", True, False),
    ("The product list displays a \"Page N of M\" indicator.", False, False),
    ("Name is required.", False, True),
])
def test_use_case_polarity(stmt, negative, has_path):
    assert use_case.is_negative(stmt) is negative
    assert use_case.has_negative_path(stmt) is has_path


def test_use_case_floor_covers_every_testable_ac(inp):
    cases = use_case.generate(inp)
    floor_acs = {a for c in cases if "floor" in c["tags"] for a in c["ac_ids"]}
    assert floor_acs == {a["id"] for a in inp.testable_acs()}
    smoke = [c for c in cases if c["level"] == "smoke"]
    assert smoke and all(inp.ac(c["ac_ids"][0])["priority"] == "P0" and c["test_type"] == "positive" for c in smoke)


def test_llm_negative_path_hint_overrides_wording(inp):
    cases = use_case.generate(inp, {"AC-02.1.3": True, "AC-01.1": False})
    keys = {c["key"] for c in cases}
    assert "uc|ac|AC-02.1.3|exception" in keys and "uc|ac|AC-01.1|exception" not in keys


def test_pairwise_on_search_form(inp):
    cases = pairwise.generate(inp)
    assert len(cases) == 16 and all(c["target"]["form_id"] == "F-4dc9438dcb" for c in cases)


# ── linking / risk / assignment / selection ───────────────────────────────────

def test_token_linking_respects_candidates_and_skips_role_cases(inp):
    cases = ep.generate(inp) + role_matrix.generate(inp) + state_transition.generate(inp)
    left = linking.link_unattributed(cases, inp)
    for c in cases:
        if c["ac_link"] == "token" and c["target"].get("form_id"):
            form = next(f for f in inp.forms if f.form_id == c["target"]["form_id"])
            assert set(c["ac_ids"]) <= set(form.ac_ids)                  # never outside the form's criteria
    assert next(c for c in cases if c["title"] == "user opening /cart by direct URL is allowed")["id"] in left
    case = {"id": "x", "technique": "ep", "title": "Name: whitespace only is rejected", "steps_outline": [],
            "oracles": [], "target": {"kind": "form", "form_id": "F-69c120ba3f", "field": "name"}}
    assert set(linking.link(case, inp)) <= {"AC-03.1.1", "AC-03.1.2", "AC-03.2.1", "AC-03.2.2", "AC-03.2.3"}


def test_risk_priority_thresholds_and_smoke_stays_p0(inp):
    assert [priority_for(r) for r in (0.95, 0.7, 0.69, 0.45, 0.3, 0.1)] == ["P0", "P0", "P1", "P1", "P2", "P3"]
    cases = use_case.generate(inp)
    score_all(cases, inp)
    assert all(c["priority"] == "P0" for c in cases if c["level"] == "smoke")
    assert all(0.0 <= c["risk_score"] <= 1.0 for c in cases)


def test_changed_page_raises_risk(inp):
    cases = bva.generate(inp)
    score_all(cases, inp)
    before = {c["id"]: c["risk_score"] for c in cases}
    inp.previous_hashes = dict(inp.page_hashes(), **{"/products/new": "different"})
    cases2 = bva.generate(inp)
    score_all(cases2, inp)
    changed = [c for c in cases2 if c["target"]["url_template"] == "/products/new"]
    assert changed and all(c["risk_score"] > before[c["id"]] and "changed-page" in c["tags"] for c in changed)


def test_assignment_routes_role_cases_to_matching_module(inp):
    cases = role_matrix.generate(inp)
    assert assign.assign(cases, inp) == []
    by = _by_title(cases)
    assert by["admin opening /admin by direct URL is allowed"]["module_id"] == "M06"
    assert by["guest opening /cart by direct URL is blocked"]["module_id"] == "M01"
    assert by["user opening /admin by direct URL is blocked"]["scenario_id"].startswith(("M02", "M03", "M04", "M05"))


def test_assignment_keeps_form_cases_in_a_module_that_can_reach_the_page(inp):
    cases = bva.generate(inp)
    assign.assign(cases, inp)
    qty = next(c for c in cases if c["target"].get("field") == "quantity")
    assert qty["module_id"] == "M04" and qty["scenario_id"] == "M04_BS_001"


def _pool(inp):
    cases = use_case.generate(inp) + bva.generate(inp) + ep.generate(inp)
    linking.link_unattributed(cases, inp)
    score_all(cases, inp)
    return cases


def test_select_keeps_p0_and_floor_and_cuts_the_rest_with_reason_budget(inp):
    pool = _pool(inp)
    testable = [a["id"] for a in inp.testable_acs()]
    selected, cut, rep = select(pool, "standard", {"max_tests": 70, "max_runtime_minutes": 999}, testable, [])
    sel_ids = {c["id"] for c in selected}
    assert all(c["id"] in sel_ids for c in pool if c["priority"] == "P0" and c["level"] in ("smoke", "standard"))
    assert set(floor_cases([c for c in pool if c["level"] in ("smoke", "standard")], testable)) <= sel_ids
    assert cut and all(c["_cut_reason"] == "budget" for c in cut)
    assert rep["selected"] == len(selected)


def test_select_runtime_budget_and_respected_flag(inp):
    pool = _pool(inp)
    testable = [a["id"] for a in inp.testable_acs()]
    _sel, _cut, rep = select(pool, "standard", {"max_tests": 1000, "max_runtime_minutes": 1}, testable, [])
    assert rep["respected"] is False and rep["p0_over_budget"] is True   # floor alone needs > 1 minute
    sel, _cut, rep = select(pool, "standard", {"max_tests": 1000, "max_runtime_minutes": 600}, testable, [])
    assert rep["respected"] is True and rep["est_runtime_minutes"] <= 600


def test_profile_filter_excludes_higher_levels(inp):
    pool = _pool(inp)
    sel, _cut, rep = select(pool, "smoke", {"max_tests": 400, "max_runtime_minutes": 45}, [], [])
    assert {c["level"] for c in sel} == {"smoke"} and rep["_excluded_by_profile"] > 0


@settings(max_examples=40, deadline=None)
@given(max_tests=st.integers(1, 300), minutes=st.floats(0.5, 120))
def test_select_property_budget_only_exceeded_by_p0_and_floor(base_inp, max_tests, minutes):
    pool = _pool(copy.deepcopy(base_inp))
    testable = [a["id"] for a in base_inp.testable_acs()]
    sel, cut, rep = select(pool, "standard", {"max_tests": max_tests, "max_runtime_minutes": minutes}, testable, [])
    must = {c["id"] for c in pool if c["priority"] == "P0" and c["level"] in ("smoke", "standard")}
    must |= set(floor_cases([c for c in pool if c["level"] in ("smoke", "standard")], testable))
    extra = [c for c in sel if c["id"] not in must]
    if extra:                                     # anything beyond the must-keep set fits the budget
        assert len(sel) <= max_tests and sum(c["est_seconds"] for c in sel) <= minutes * 60
    assert len({c["id"] for c in sel} | {c["id"] for c in cut}) == len(sel) + len(cut)
