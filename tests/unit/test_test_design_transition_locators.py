"""State-transition cases get a locator key for their trigger on its own page (tools/test_design/locators.py).

Before: the case said only "click 'Log in'" and the plan picked the "Log in" BUTTON of the login form (key log_in) for
the "Log in" nav LINK on /help — a 15 s timeout on a correct app."""

import shutil
from pathlib import Path

import pytest

from tools.test_design import design as D
from tools.test_design.inputs import DesignInputs
from tools.test_design.locators import merge_transition_locators

FIX = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module")
def designed(tmp_path_factory):
    d = tmp_path_factory.mktemp("p")
    (d / "test_comprehension").mkdir()
    for n in ("requirements", "business_scenarios", "app_map", "form_model"):
        shutil.copy(FIX / "recorded" / "buggy_shop" / f"{n}.json", d / "test_comprehension")
    shutil.copy(FIX / "test_design" / "buggy_shop" / "project.yaml", d)
    inp = DesignInputs.load(str(d), "b")
    cases, _ = D.generate_all(inp, {})
    return inp, cases


def test_trigger_key_points_at_the_element_on_the_source_page(designed):
    inp, cases = designed
    existing = {"log_in": {"type": "role", "locator": "button", "name": "Log in"}}       # the login form's button
    merged, added = merge_transition_locators(existing, inp, cases)
    case = next(c for c in cases if c.get("key") == "st|0|/help|/login|Log in")
    key = case["locator_keys"]["trigger"]
    assert key != "log_in" and merged[key]["locator"] == '[data-testid="nav-login"]' and key in added
    assert merged["log_in"] == existing["log_in"]                                         # untouched


def test_a_test_id_shared_by_list_items_is_never_used(designed):
    inp, cases = designed
    merged, _ = merge_transition_locators({}, inp, cases)
    product = next(c for c in cases if (c.get("key") or "").startswith("st|0|/products|/products/{id}|"))
    entry = merged[product["locator_keys"]["trigger"]]
    assert entry["type"] == "role" and entry["locator"] == "link"          # by its own name, not product-link


def test_most_transitions_get_a_trigger_and_keys_are_stable(designed):
    inp, cases = designed
    trans = [c for c in cases if c["technique"] == "state_transition" and (c.get("target") or {}).get("kind") == "transition"]
    m1, _ = merge_transition_locators({}, inp, cases)
    assert sum(1 for c in trans if c.get("locator_keys", {}).get("trigger")) >= len(trans) - 1
    m2, added2 = merge_transition_locators(m1, inp, cases)
    assert m2 == m1 and added2 == []                                                     # re-runs add nothing


def test_field_invalid_only_where_a_probe_saw_it(designed):
    """buggy_shop's product form validates in its own script (novalidate, errors in an alert, no request): the
    field is never marked invalid — only the login form's native `required` is."""
    _inp, cases = designed

    def oracles(fragment):
        c = next(c for c in cases if fragment in c["title"])
        return [o["type"] for o in c["oracles"]]
    assert oracles("Name length max+1")[:1] == ["submission_rejected"]
    assert {"no_request", "url_unchanged"} <= set(oracles("Name length max+1"))     # the probe sent nothing
    assert oracles("Price range min-1")[0] == "submission_rejected"
    assert oracles("Username: empty")[0] == "field_invalid"                          # native required, blocked


def test_accept_cases_on_a_stateful_field_are_cut_with_the_reason(designed):
    """White-box: POST /cart/add adds the quantity to what the cart holds — 'max (99) accepted' then depends on
    what earlier tests left in the cart. The accept side is cut with the reason; the reject side stays."""
    from tools.test_design.design import _cut_stateful_accepts
    inp, cases = designed
    form = next(f for f in inp.forms if f.dom_id == "add-to-cart-form")
    inp.stateful = {form.form_id: ["quantity"]}
    keep, cut = _cut_stateful_accepts(cases, inp)
    titles = {c["title"] for c in cut}
    assert titles and all("accepted" in t for t in titles) and all(c["_cut_reason"] == "stateful" for c in cut)
    assert any("max+1" in c["title"] for c in keep if (c.get("target") or {}).get("form_id") == form.form_id)


def test_a_native_message_without_a_blocked_submit_is_not_field_invalid():
    """2026-10-16 run: add-to-cart is novalidate — the browser had a message for quantity 0 but did not block, the
    page posted and re-rendered, and verifyFieldInvalid timed out."""
    from tools.test_design.cases import rejection_oracles
    from tools.test_design.inputs import Field, Form
    fld = Field(form_id="F", name="quantity", label="Quantity", type="number", locator=None, required=False,
                constraints={}, messages={}, options=[], default_value=None)
    for blocked, want in ((False, "submission_rejected"), (True, "field_invalid")):
        frm = Form.__new__(Form)                         # only what rejection_oracles reads
        frm.method, frm.action = "post", "/cart/add"
        frm.probes = [{"probe": "below_min", "field": "quantity", "aria_invalid": [], "network": [{"method": "POST"}],
                       "native": {"blocked": blocked, "messages": {"quantity": "Value must be greater than or equal to 1."}}}]
        assert rejection_oracles(frm, fld, [], ["below_min"])[0]["type"] == want
