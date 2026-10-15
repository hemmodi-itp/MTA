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
