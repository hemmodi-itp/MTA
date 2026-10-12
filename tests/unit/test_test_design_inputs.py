"""Phase 3 — constraint parsing, AC ↔ field linking and input normalisation (tools/test_design/constraints, inputs)."""

import os

import pytest

from tools.test_design.constraints import message_kind, parse_constraints, quoted_messages, split_clauses
from tools.test_design.inputs import DesignInputs, Field, _merge_constraint, valid_value_for

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "test_design", "buggy_shop")


@pytest.fixture(scope="module")
def inp():
    return DesignInputs.load(FIXTURE, "bench_buggy_shop")


# ── constraints.py ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("Name must be 1–50 characters.", {"length": {"min": 1, "max": 50}}),
    ("Name must be 1-50 characters.", {"length": {"min": 1, "max": 50}}),
    ("A name of 51 or more characters is rejected", {"length": {"max": 50}}),
    ("A name of exactly 50 characters is accepted.", {"length": {"boundary": 50}}),
    ("Description must be at most 500 characters", {"length": {"max": 500}}),
    ("Password must be at least 8 characters", {"length": {"min": 8}}),
    ("Quantity must be a whole number from 1 to 99", {"range": {"min": 1, "max": 99, "integer": True}}),
    ("must be zero or more", {"range": {"min": 0}}),
    ("Files over 1 MB are rejected", {"size": {"max": 1048576}}),
    ("a file of at most 2 MB", {"size": {"max": 2097152}}),
    ("Category must be one of Books, Electronics or Home", {"options": {"values": ["Books", "Electronics", "Home"]}}),
    ("Only CSV or PNG files are allowed", {"accept": {"values": [".csv", ".png"]}}),
    ("Description is optional", {"required": {"value": False}}),
    ("The date must be between 2024-01-01 and 2024-12-31", {"date": {"min": "2024-01-01", "max": "2024-12-31"}}),
    ("Search matches any product whose name contains the search text", {}),
])
def test_parse_constraints(text, expected):
    assert parse_constraints(text) == expected


def test_price_rule_has_decimals_range_and_required():
    c = parse_constraints("Price is required, numeric with at most 2 decimals, and must be zero or more.")
    assert c == {"range": {"min": 0}, "decimals": {"max": 2}, "required": {"value": True}}


def test_quoted_messages_and_kinds():
    msgs = quoted_messages('Rejected with "Name is required"; or “Name must be at most 50 characters”, not "mouse".')
    assert msgs == ["Name is required", "Name must be at most 50 characters"]
    assert message_kind("Name is required") == "required_missing"
    assert message_kind("Name must be at most 50 characters") == "too_long"
    assert message_kind("Quantity must be between 1 and 99") == "out_of_range"
    assert message_kind("Only CSV or PNG files are allowed") == "wrong_accept"
    assert message_kind("File must be 1 MB or smaller") == "too_large"
    assert message_kind("Product deleted") is None


def test_split_clauses_keeps_quoted_semicolons():
    assert split_clauses('Name is required; it shows "a; b". Done.') == ["Name is required", 'it shows "a; b".', "Done."]


# ── precedence ────────────────────────────────────────────────────────────────

def test_dom_bound_beats_brd_and_observed_but_missing_bounds_fill_in():
    f = Field(form_id="F", name="qty", label="Qty", type="number", locator=None, required=False,
              constraints={}, messages={}, options=[], default_value=None)
    _merge_constraint(f, "range", {"min": 1}, "dom")
    _merge_constraint(f, "range", {"min": 0, "max": 99}, "brd")
    _merge_constraint(f, "range", {"max": 50}, "observed")
    r = f.constraints["range"]
    assert (r["min"], r["max"]) == (1, 99)
    assert r["sources"] == {"min": "dom", "max": "brd"}


# ── linking on the frozen buggy_shop artifacts ────────────────────────────────

def _form(inp, template, dom_id):
    return next(f for f in inp.forms if f.url_template == template and f.dom_id == dom_id)


def _field(form, name):
    return next(f for f in form.fields if f.name == name)


def test_query_variant_form_is_folded_into_its_page(inp):
    assert [f.url_template for f in inp.forms if f.dom_id == "search-form"] == ["/products"]


def test_product_name_links_only_its_own_criteria(inp):
    name = _field(_form(inp, "/products/new", "product-form"), "name")
    assert name.ac_ids == ["AC-03.1.1", "AC-03.1.2", "AC-03.2.1", "AC-03.2.2", "AC-03.2.3"]
    assert "AC-04.1" not in name.ac_ids                       # "file name" ≠ the product's Name field
    assert name.constraints["length"]["max"] == 50 and name.constraints["length"]["min"] == 1
    assert name.messages["too_long"] == {"text": "Name must be at most 50 characters", "source": "brd",
                                         "ac_id": "AC-03.2.3"}
    assert name.kind_acs["length"] == ["AC-03.2.1", "AC-03.2.2", "AC-03.2.3"]


def test_owned_form_wins_over_other_modules_forms(inp):
    search_category = _field(_form(inp, "/products", "search-form"), "category")
    assert "AC-03.4.1" not in search_category.ac_ids          # product-form category rule, not the filter
    assert "required_missing" not in search_category.messages


def test_api_and_non_functional_criteria_are_not_linked_to_fields(inp):
    for form in inp.forms:
        for f in form.fields:
            assert not {"AC-03.8", "AC-01.4", "AC-02.7"} & set(f.ac_ids)


def test_dom_range_kept_and_brd_criteria_attributed(inp):
    qty = _field(_form(inp, "/products/{id}", "add-to-cart-form"), "quantity")
    assert (qty.constraints["range"]["min"], qty.constraints["range"]["max"]) == (1, 99)
    assert qty.constraints["range"]["sources"]["min"] == "dom"
    assert qty.kind_acs["range"] == ["AC-05.1.1", "AC-05.1.2"]


def test_twin_form_inherits_links(inp):
    edit = _form(inp, "/products/{id}/edit", "product-form")
    new = _form(inp, "/products/new", "product-form")
    assert edit.twin_of == new.form_id and edit.ac_ids == new.ac_ids
    assert _field(edit, "name").kind_acs == _field(new, "name").kind_acs


def test_form_modules_and_module_roles(inp):
    assert _form(inp, "/products/{id}", "add-to-cart-form").module_id == "M04"     # by its criteria (cart)
    assert _form(inp, "/products/new", "product-form").module_id == "M03"          # exact module URL
    assert {m["id"]: m["role"] for m in inp.modules} == {"M01": "guest", "M02": "user", "M03": "user",
                                                         "M04": "user", "M05": "user", "M06": "admin"}


def test_valid_filler_values_respect_constraints(inp):
    new = _form(inp, "/products/new", "product-form")
    assert valid_value_for(_field(new, "category")) == "Books"
    assert valid_value_for(_field(new, "price")) == "0"
    assert 1 <= len(valid_value_for(_field(new, "name"))) <= 50
    qty = _field(_form(inp, "/products/{id}", "add-to-cart-form"), "quantity")
    assert valid_value_for(qty) == "1"


def test_missing_phase2_artifacts_are_limitations_not_errors():
    i = DesignInputs.from_artifacts("p", {}, {"requirements": []}, {"scenarios": []})
    assert i.forms == [] and i.states == {} and len(i.limitations) == 3
