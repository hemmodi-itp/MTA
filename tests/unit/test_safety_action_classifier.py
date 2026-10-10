"""Phase 0.5 — deterministic action-safety classifier (tools/safety/action_classifier.py).

The labelled set below is the classifier's contract: >= 30 names required by the
plan (46 here). Each entry is (accessible name, expected destructive?, expected
category or None). Tune destructive_rules.yaml, never these labels, unless a label
is genuinely wrong.
"""

import pytest

from tools.safety.action_classifier import (
    classify,
    classify_step,
    classify_text,
    classify_url,
    words_of,
)

LABELLED_NAMES = [
    # ── destructive ──────────────────────────────────────────────────────────
    ("Delete account", True, "delete"),
    ("Delete", True, "delete"),
    ("Remove item", True, "delete"),
    ("Remove from cart", True, "delete"),
    ("Destroy project", True, "delete"),
    ("Erase all data", True, "delete"),
    ("Purge cache", True, "delete"),
    ("Move to trash", True, "delete"),
    ("Discard draft", True, "delete"),
    ("Pay now", True, "payment"),
    ("Pay $49.99", True, "payment"),
    ("Purchase", True, "payment"),
    ("Buy now", True, "payment"),
    ("Place order", True, "payment"),
    ("Confirm order", True, "payment"),
    ("Complete purchase", True, "payment"),
    ("Submit payment", True, "payment"),
    ("Send", True, "send"),
    ("Send message", True, "send"),
    ("Send invitation", True, "send"),
    ("Transfer funds", True, "transfer"),
    ("Withdraw", True, "transfer"),
    ("Deactivate user", True, "account"),
    ("Close account", True, "account"),
    ("Unsubscribe", True, "account"),
    ("Cancel subscription", True, "account"),
    ("Cancel order", True, "account"),
    ("Revoke access", True, "account"),
    ("Terminate instance", True, "account"),
    ("Reset password", True, "reset"),
    ("Reset account", True, "reset"),
    ("DELETE ACCOUNT", True, "delete"),
    # ── not destructive ──────────────────────────────────────────────────────
    ("Cancel", False, None),
    ("Search", False, None),
    ("Login", False, None),
    ("Log in", False, None),
    ("Submit", False, None),
    ("Save", False, None),
    ("Next page", False, None),
    ("Remove filter", False, None),
    ("Remove all filters", False, None),
    ("Reset filters", False, None),
    ("Reset form", False, None),
    ("Payment history", False, None),   # "pay" is a whole word only
    ("Resend code", False, None),
    ("Add to cart", False, None),
    ("Sender address", False, None),
    ("Deleted items folder", False, None),
]


def test_labelled_set_is_large_enough():
    assert len(LABELLED_NAMES) >= 30
    assert sum(1 for _, d, _ in LABELLED_NAMES if d) >= 15
    assert sum(1 for _, d, _ in LABELLED_NAMES if not d) >= 15


@pytest.mark.parametrize("name,destructive,category", LABELLED_NAMES)
def test_labelled_click_names(name, destructive, category):
    verdict = classify("click", accessible_name=name)
    assert verdict.destructive is destructive, verdict
    if destructive:
        assert verdict.category == category


@pytest.mark.parametrize("action", ["verifyVisible", "verifyText", "enterText", "waitForElement", "hover"])
def test_non_interaction_actions_never_destructive(action):
    assert classify(action, accessible_name="Delete account").destructive is False


@pytest.mark.parametrize("url,destructive", [
    ("/users/42/delete", True),
    ("https://shop.test/account/deactivate?id=1", True),
    ("/items?action=delete&id=3", True),
    ("/checkout/place-order", True),
    ("/products", False),
    ("/deleted-items", False),
    ("/payment-history", False),
    (None, False),
])
def test_url_rules(url, destructive):
    assert classify_url(url).destructive is destructive


def test_navigate_classified_by_url_only():
    assert classify("navigate", accessible_name="Delete account", url="/products").destructive is False
    assert classify("navigate", url="/account/delete").destructive is True


def test_identifier_words_count():
    assert words_of("deleteAccountBtn") == "delete account btn"
    assert words_of("#delete-account") == "delete account"
    verdict = classify("click", accessible_name="", extra_text=["deleteAccountBtn"])
    assert verdict.destructive and verdict.category == "delete"


def test_safe_phrase_overrides_destructive_word():
    assert classify_text("Reset filters").destructive is False
    assert classify_text("Reset password").destructive is True


LOCATOR_MAP = {
    "delete_account_button": {"type": "role", "locator": "button", "name": "Delete account"},
    "search_button": {"type": "role", "locator": "button", "name": "Search"},
    "pay_link": {"type": "text", "locator": "Pay now"},
    "danger_zone": {"type": "testid", "locator": "purge-everything"},
    "plain_css": {"type": "css", "locator": "#submit-btn"},
    "status_select": {"type": "label", "locator": "Status"},
}


@pytest.mark.parametrize("step,destructive", [
    ({"action": "click", "locator_key": "delete_account_button"}, True),
    ({"action": "doubleClick", "locator_key": "delete_account_button"}, True),
    ({"action": "click", "locator_key": "search_button"}, False),
    ({"action": "click", "locator_key": "pay_link"}, True),
    ({"action": "click", "locator_key": "danger_zone"}, True),
    ({"action": "click", "locator_key": "plain_css"}, False),
    ({"action": "verifyVisible", "locator_key": "delete_account_button"}, False),
    ({"action": "pressKey", "locator_key": "delete_account_button", "value": "Enter"}, True),
    ({"action": "pressKey", "locator_key": "delete_account_button", "value": "Tab"}, False),
    ({"action": "selectDropdownByText", "locator_key": "status_select", "value": "Delete"}, True),
    ({"action": "selectDropdownByText", "locator_key": "status_select", "value": "Active"}, False),
    ({"action": "navigate", "value": "/admin/users/1/delete"}, True),
    ({"action": "click", "locator_key": "unknown_key"}, False),
    ({"action": "dragAndDrop", "locator_key": "plain_css", "target_locator_key": "danger_zone"}, True),
])
def test_classify_step_against_locator_map(step, destructive):
    assert classify_step(step, LOCATOR_MAP).destructive is destructive


def test_classify_step_tolerates_garbage():
    assert classify_step("not a step").destructive is False
    assert classify_step({}).destructive is False
