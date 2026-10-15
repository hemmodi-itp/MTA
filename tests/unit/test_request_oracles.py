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
    assert out["tests"][0]["steps"][-1] == {"action": "verifyRequest", "method": "POST", "urlPattern": "/login",
                                           "status": "success", "bodyContains": "alice"}
    assert [c["change"] for c in changes] == ["rewritten", "status"]
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
