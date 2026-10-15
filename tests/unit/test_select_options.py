"""Generated plans choose only options a <select> really has (tools/test_creation/select_options.py)."""

from tools.test_creation.select_options import ground_selects, select_options

FORM_MODEL = {"forms": [{"form_id": "F-1", "fields": [{"name": "category", "constraints": {"options": [
    {"value": "", "text": "Choose a category"}, {"value": "Books", "text": "Books"},
    {"value": "home", "text": "Home"}, {"value": "x", "text": "Retired", "disabled": True}]}}]}]}
LMAP = {"category_2": {"type": "css", "locator": '#product-form [name="category"]', "_form_id": "F-1"},
        "name": {"type": "css", "locator": '#product-form [name="name"]', "_form_id": "F-1"}}
OPTS = select_options(LMAP, FORM_MODEL)


def _plan(value, action="selectDropdownByText", type_="negative", case_id=None):
    return {"tests": [{"name": "t", "type": type_, "case_id": case_id, "steps": [
        {"action": "enterText", "locator_key": "name", "value": ""},
        {"action": action, "locator_key": "category_2", "value": value}]}]}


def test_options_come_from_the_form_model_without_placeholder_or_disabled():
    assert list(OPTS) == ["category_2"] and [o["text"] for o in OPTS["category_2"]["options"]] == ["Books", "Home"]


def test_real_options_are_kept_by_text_or_value_case_insensitively():
    for v, action in (("Books", "selectDropdownByText"), ("home", "selectDropdownByText"), ("HOME", "selectDropdownByValue")):
        assert ground_selects(_plan(v, action), OPTS)[1] == []


def test_an_invented_option_on_a_filler_select_becomes_a_real_one():
    out, changes = ground_selects(_plan("Furniture"), OPTS)
    assert out["tests"][0]["steps"][1]["value"] == "Books" and changes[0]["change"] == "option replaced"
    out, _ = ground_selects(_plan("Furniture", "selectDropdownByValue"), OPTS)
    assert out["tests"][0]["steps"][1]["value"] == "Books"


def test_a_negative_case_on_the_select_itself_is_dropped():
    cases = {"TC-1": {"target": {"kind": "form", "field": "category"}}}
    out, changes = ground_selects(_plan("Furniture", case_id="TC-1"), OPTS, cases)
    assert out["tests"] == [] and changes[0]["change"] == "dropped" and "through the API" in changes[0]["reason"]
