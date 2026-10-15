"""A positive submit fills every field the form requires (tools/test_creation/required_fields.py)."""

from tools.test_creation.required_fields import complete_required_fields

FM = {"forms": [{"form_id": "F-1", "dom_id": "product-form", "method": "post", "url_template": "/products/new",
                 "submit": {"text": "Save product"}, "fields": [
                     {"name": "name", "type": "text", "constraints": {"effective_required": True, "maxlength": 50}},
                     {"name": "price", "type": "text", "constraints": {"effective_required": True}},
                     {"name": "category", "type": "select", "constraints": {"effective_required": True, "options": [
                         {"value": "", "text": "Choose"}, {"value": "Books", "text": "Books"}]}},
                     {"name": "photo", "type": "file", "constraints": {"effective_required": True}},
                     {"name": "description", "type": "textarea", "constraints": {"effective_required": False}}]}]}
LM = {"name_2": {"type": "role", "locator": "textbox", "name": "Name", "_fingerprint": {"attrs": {"name": "name"}}},
      "price": {"type": "css", "locator": '#product-form [name="price"]', "_form_id": "F-1"},
      "category_2": {"type": "css", "locator": '#product-form [name="category"]', "_form_id": "F-1"},
      "save": {"type": "role", "locator": "button", "name": "Save product"}}


def _plan(type_="positive"):
    return {"tests": [{"name": "save", "type": type_, "steps": [
        {"action": "navigate", "value": "/products/new"},
        {"action": "enterText", "locator_key": "name_2", "value": "Desk"},
        {"action": "click", "locator_key": "save"},
        {"action": "verifyUrlContains", "value": "/products"}]}]}


def test_missing_required_fields_are_filled_before_the_submit():
    out, changes = complete_required_fields(_plan(), LM, FM, valid_values={("F-1", "price"): "0"})
    steps = out["tests"][0]["steps"]
    assert [s["action"] for s in steps] == ["navigate", "enterText", "enterText", "selectDropdownByText", "click",
                                           "verifyUrlContains"]
    assert steps[2] == {"action": "enterText", "locator_key": "price", "value": "0"}         # test design's value
    assert steps[3]["value"] == "Books"                                                       # placeholder skipped
    assert [c["field"] for c in changes] == ["price", "category", "photo"]
    assert changes[2]["change"] == "required field not filled"                                 # a file is reported


def test_without_a_design_value_text_respects_the_length_limit():
    fm = {"forms": [dict(FM["forms"][0], fields=[{"name": "name", "type": "text",
                                                  "constraints": {"effective_required": True, "maxlength": 5}}])]}
    plan = {"tests": [{"name": "t", "type": "positive", "steps": [{"action": "navigate", "value": "/products/new"},
                                                                  {"action": "click", "locator_key": "save"}]}]}
    out, _ = complete_required_fields(plan, LM, fm)
    assert out["tests"][0]["steps"][1] == {"action": "enterText", "locator_key": "name_2", "value": "Valid"}


def test_negative_tests_and_other_pages_are_untouched():
    assert complete_required_fields(_plan("negative"), LM, FM)[1] == []
    other = _plan()
    other["tests"][0]["steps"][0]["value"] = "/cart"
    assert complete_required_fields(other, LM, FM)[1] == []
