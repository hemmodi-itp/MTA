"""Request oracles are grounded in the endpoints discovery observed (tools/test_creation/request_oracles.py)."""

import json
from pathlib import Path

from tools.test_creation.request_oracles import ground_plan, known_endpoints, match

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "buggy_shop"
EPS = known_endpoints(json.loads((REC / "form_model.json").read_text(encoding="utf-8")),
                      json.loads((REC / "api_inventory.json").read_text(encoding="utf-8")))


def _test(name, steps):
    return {"tests": [{"name": name, "steps": steps}]}


def test_endpoints_merge_forms_and_traffic():
    login = match("POST", "/login", EPS)
    assert login["template"] == "/login" and login["pages"] == ["/login"] and login["statuses"] == {"401": 2}
    assert match("POST", "/products/*/edit", EPS)["template"] == "/products/{id}/edit"
    assert match("POST", "/api/login", EPS) is None and match("GET", "/login", EPS)["method"] == "GET"


def test_an_invented_endpoint_is_rewritten_to_the_form_the_test_submits():
    plan = _test("valid login", [{"action": "navigate", "value": "/login"},
                                 {"action": "enterText", "locator_key": "username", "value": "alice"},
                                 {"action": "click", "locator_key": "log_in"},
                                 {"action": "verifyRequest", "method": "POST", "urlPattern": "/api/login",
                                  "status": "2xx", "bodyContains": "alice"}])
    out, changes = ground_plan(plan, EPS)
    # POST /login was only seen answering 401 (discovery's invalid-input probes): no status is asserted
    assert out["tests"][0]["steps"][-1] == {"action": "verifyRequest", "method": "POST", "urlPattern": "/login",
                                           "bodyContains": "alice"}
    assert [c["change"] for c in changes] == ["rewritten", "status dropped"]
    assert plan["tests"][0]["steps"][-1]["urlPattern"] == "/api/login"          # the input is not mutated


def test_unknown_endpoint_without_a_single_form_is_dropped():
    plan = _test("t", [{"action": "navigate", "value": "/products/3"},       # add-to-cart + delete: ambiguous
                       {"action": "verifyNoRequest", "method": "POST", "urlPattern": "/api/orders"},
                       {"action": "verifyUrlContains", "value": "/products/3"}])
    out, changes = ground_plan(plan, EPS)
    assert [s["action"] for s in out["tests"][0]["steps"]] == ["navigate", "verifyUrlContains"]
    assert changes[0]["change"] == "dropped"


def test_known_endpoint_kept_status_relaxed_only_when_never_seen_and_body_needs_typed_value():
    plan = _test("t", [{"action": "navigate", "value": "/products/new"},
                       {"action": "enterText", "locator_key": "name", "value": "Lamp"},
                       {"action": "verifyRequest", "method": "POST", "urlPattern": "/cart/add", "status": "3xx"},
                       {"action": "verifyRequest", "method": "POST", "urlPattern": "/products", "status": "2xx",
                        "bodyContains": "Desk"},
                       {"action": "verifyRequest", "method": "GET", "urlPattern": "/cart", "status": 200}])
    out, changes = ground_plan(plan, EPS)
    steps = out["tests"][0]["steps"]
    assert steps[2]["status"] == "3xx"                       # /cart/add was seen answering 303: kept
    assert steps[3] == {"action": "verifyRequest", "method": "POST", "urlPattern": "/products", "status": "success"}
    assert steps[4]["status"] == 200                         # an exact status is the author's call
    assert [c["change"] for c in changes] == ["status", "bodyContains dropped"]   # a form submit nobody observed


def test_an_api_route_known_only_from_code_is_not_what_the_ui_form_posts():
    eps = known_endpoints(json.loads((REC / "form_model.json").read_text(encoding="utf-8")), {},
                          {"routes": [{"method": "POST", "path_template": "/api/products"}]})
    plan = _test("save", [{"action": "navigate", "value": "/products/new"},
                          {"action": "click", "locator_key": "save_product_button"},
                          {"action": "verifyRequest", "method": "POST", "urlPattern": "/api/products*", "status": "2xx"}])
    out, changes = ground_plan(plan, eps)
    assert out["tests"][0]["steps"][-1] == {"action": "verifyRequest", "method": "POST", "urlPattern": "/products",
                                           "status": "success"}
    alone = _test("api", [{"action": "verifyRequest", "method": "POST", "urlPattern": "/api/products"}])
    assert ground_plan(alone, eps)[1] == []          # no form submitted: the code route is a legitimate target


def test_without_discovery_the_plan_is_untouched():
    plan = _test("t", [{"action": "verifyRequest", "method": "POST", "urlPattern": "/anything"}])
    assert ground_plan(plan, []) == (plan, [])


def test_a_wildcard_means_the_form_the_test_submits():
    plan = _test("save", [{"action": "navigate", "value": "/products/new"},
                          {"action": "click", "locator_key": "save_product_button"},
                          {"action": "verifyRequest", "method": "POST", "urlPattern": "*", "status": "2xx"}])
    out, _ = ground_plan(plan, EPS)
    assert out["tests"][0]["steps"][-1] == {"action": "verifyRequest", "method": "POST", "urlPattern": "/products",
                                           "status": "success"}
    loose = _test("x", [{"action": "verifyRequest", "method": "POST", "urlPattern": "*", "status": "2xx"}])
    out, changes = ground_plan(loose, EPS)                   # no page, no form: kept, but any success will do
    assert out["tests"][0]["steps"][-1]["urlPattern"] == "*" and out["tests"][0]["steps"][-1]["status"] == "success"



def test_reconcile_strips_field_invalid_the_case_does_not_back():
    from agents.test_creation.script_generation.agent import _strip_unbacked_field_invalid
    steps = [{"action": "enterText", "locator_key": "price", "value": "-0.01"}, {"action": "click", "locator_key": "save"},
             {"action": "verifyFieldInvalid", "locator_key": "price"},
             {"action": "verifyContainsText", "locator_key": "errors", "value": "Price must be zero or more"}]
    case = {"oracles": [{"type": "submission_rejected", "field": "price"}, {"type": "error_text", "contains": "x"}]}
    out = _strip_unbacked_field_invalid({"name": "t", "steps": steps}, case)
    assert [s["action"] for s in out["steps"]] == ["enterText", "click", "verifyContainsText"]
    assert out["removed_oracles"] == ["verifyFieldInvalid x1: no probe saw the field marked invalid"]
    backed = {"oracles": [{"type": "field_invalid", "field": "price"}]}
    assert _strip_unbacked_field_invalid({"name": "t", "steps": steps}, backed)["steps"] == steps


def test_a_failed_login_journey_does_not_expect_success():
    """2026-10-16 run: 'Journey: Failed Login' asked for POST /login 'success' — the grounding itself had added it."""
    plan = _test("failed login", [{"action": "navigate", "value": "/login"},
                                  {"action": "enterText", "locator_key": "password", "value": "WrongPassword999!"},
                                  {"action": "click", "locator_key": "log_in_button"},
                                  {"action": "verifyRequest", "method": "POST", "urlPattern": "/login", "status": "2xx"}])
    out, ch = ground_plan(plan, EPS)
    assert "status" not in out["tests"][0]["steps"][-1] and ch[0]["change"] == "status dropped"
    neg = _test("neg", [{"action": "navigate", "value": "/cart"},
                        {"action": "verifyRequest", "method": "POST", "urlPattern": "/cart/add", "status": "3xx"}])
    neg["tests"][0]["type"] = "negative"
    assert "status" not in ground_plan(neg, EPS)[0]["tests"][0]["steps"][-1]


def test_record_ids_discovery_never_saw():
    """2026-10-16 run: verifyApiState GET /api/orders/10042 — no such order; discovery saw none at all."""
    from tools.test_creation.request_oracles import ground_record_ids, observed_paths
    seen = observed_paths({"states": [{"url": "http://a.test/products/3"}, {"url": "http://a.test/products/3/edit"},
                                      {"url": "http://a.test/cart"}]})
    assert seen == {"/products/{id}": ["/products/3"], "/products/{id}/edit": ["/products/3/edit"]}
    plan = _test("t", [{"action": "navigate", "value": "http://a.test/products/987"},
                       {"action": "verifyApiState", "method": "GET", "url": "/api/products/55", "expect": {"status": 200}},
                       {"action": "verifyApiState", "method": "GET", "url": "/api/orders/10042", "expect": {"status": 200}},
                       {"action": "verifyUrlContains", "value": "/products/"}])
    out, ch = ground_record_ids(plan, seen)
    steps = out["tests"][0]["steps"]
    assert steps[0]["value"] == "http://a.test/products/3" and steps[1]["url"] == "/api/products/3"   # /api mirror
    assert len(steps) == 3 and [c["change"] for c in ch] == ["record id replaced", "record id replaced", "step dropped"]
    only = _test("o", [{"action": "verifyApiState", "method": "GET", "url": "/api/orders/10042", "expect": {"status": 200}}])
    assert ground_record_ids(only, seen)[0]["tests"] == []                       # nothing left to verify
    known = _test("k", [{"action": "navigate", "value": "/products/3"}, {"action": "verifyVisible", "locator_key": "x"}])
    assert ground_record_ids(known, seen)[1] == []


def test_an_accepting_case_gets_no_llm_field_invalid_either():
    """2026-10-16 final run: 'HTML in the description is shown escaped' (accepted) carried a verifyFieldInvalid."""
    from agents.test_creation.script_generation.agent import _strip_unbacked_field_invalid
    steps = [{"action": "verifyNoDialog"}, {"action": "verifyFieldInvalid", "locator_key": "description"}]
    out = _strip_unbacked_field_invalid({"name": "t", "steps": steps},
                                        {"oracles": [{"type": "criterion_violation_handled"}]})
    assert [s["action"] for s in out["steps"]] == ["verifyNoDialog"]

