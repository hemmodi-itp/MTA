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


def test_text_in_a_number_input_drops_a_negative_test_and_fixes_a_positive_one():
    from tools.test_creation.select_options import ground_number_inputs, number_inputs
    nums = number_inputs({"quantity": {"_fingerprint": {"attrs": {"type": "number"}}}, "name": {"_fingerprint": {"attrs": {"type": "text"}}}})
    assert nums == {"quantity"}

    def plan(type_, value):
        return {"tests": [{"name": "t", "type": type_, "steps": [{"action": "enterText", "locator_key": "quantity", "value": value}]}]}
    out, ch = ground_number_inputs(plan("negative", "abc"), nums)
    assert out["tests"] == [] and ch[0]["change"] == "dropped"
    out, ch = ground_number_inputs(plan("positive", "two"), nums)
    assert out["tests"][0]["steps"][0]["value"] == "1"
    for v in ("0", "-1", "2.5", "100"):
        assert ground_number_inputs(plan("negative", v), nums)[1] == []      # numbers are typed fine
