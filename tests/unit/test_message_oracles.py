"""Expected error texts come from the BRD or the app (tools/test_creation/message_oracles.py)."""

from tools.test_creation.message_oracles import error_keys, ground_messages, known_messages

FM = {"forms": [{"probes": [{"visible_errors": [{"text": "Name is required"}]}],
                 "fields": [{"name": "price", "observed_messages": {"required_missing": {"text": "Price is required"}}}]}]}
REQS = {"requirements": [{"acceptance_criteria": [
    {"statement": 'A negative price is rejected with "Price must be zero or more".'},
    {"statement": 'The footer has a "Help" link.'}]}]}
MSGS = known_messages(FM, REQS)
ERR = error_keys({"product_form_errors": {"_dynamic": True}, "price": {"description": "Price field"}})


def _neg(value, type_="negative"):
    return {"tests": [{"name": "t", "type": type_, "steps": [
        {"action": "enterText", "locator_key": "price", "value": "-1"},
        {"action": "verifyContainsText", "locator_key": "product_form_errors", "value": value}]}]}


def test_known_messages_and_error_areas():
    assert MSGS == ["Name is required", "Price is required", "Price must be zero or more", "Help"]
    assert ERR == {"product_form_errors"}


def test_a_known_message_or_part_of_one_is_kept():
    for v in ("Price must be zero or more", "zero or more"):
        assert ground_messages(_neg(v), MSGS, ERR)[1] == []


def test_a_close_paraphrase_becomes_the_real_message():
    out, ch = ground_messages(_neg("Price must be zero or higher"), MSGS, ERR)
    assert out["tests"][0]["steps"][1]["value"] == "Price must be zero or more" and ch[0]["change"] == "message replaced"


def test_an_invented_paraphrase_of_the_field_message_is_corrected():
    out, _ = ground_messages(_neg("price must be greater than or equal to 0"), MSGS, ERR)
    assert out["tests"][0]["steps"][1]["value"] == "Price must be zero or more"


def test_an_invented_message_is_not_asserted_but_the_error_still_is():
    out, ch = ground_messages(_neg("The value could not be saved, try again"), MSGS, ERR)
    assert out["tests"][0]["steps"][1] == {"action": "verifyVisible", "locator_key": "product_form_errors"}
    assert ch[0]["change"] == "message not asserted"
    assert ground_messages(_neg("Help text is wrong"), MSGS, ERR)[1]          # "Help" alone vouches for nothing


def test_positive_tests_and_other_locators_are_untouched():
    assert ground_messages(_neg("anything", type_="positive"), MSGS, ERR)[1] == []
