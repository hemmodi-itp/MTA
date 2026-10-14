"""Phase 5 (complete): renderer golden output for every oracle action, plan validation, linter rule table,
oracles from test_cases.json (5.4), BRD-vs-observed conflicts and low-confidence oracles (5.2)."""
import json

import pytest

from agents.common.failure_classifier import LLMResponseValidationError
from agents.test_creation.script_generation import agent as sg
from agents.test_creation.script_generation.agent import ALLOWED_ACTIONS, _validate_plan
from tools.reporting import summary as qs
from tools.state.review_queue import flag_expected_value_conflicts
from tools.test_creation import assertion_linter as L
from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan, step_title

SPEC = "projects/p/test_creation/test_scripts/M/a.spec.ts"
KEYS = {"save", "name", "err", "row", "export", "help_link", "list", "q", "go", "msg", "price"}


def T(steps, type="positive", **kw):
    return {"name": "t", "type": type, "steps": steps, **kw}


def render(steps, **kw):
    return render_spec_from_plan({"tests": [T(steps)]}, {"scenario_id": "S"}, "", SPEC, **kw)


def validate(steps):
    _validate_plan({"tests": [T(steps)]}, "S", ALLOWED_ACTIONS, KEYS, {})


# ── renderer golden lines ──────────────────────────────────────────────────

GOLDEN = [
    ({"action": "verifyRequest", "method": "post", "urlPattern": "/api/x", "status": "2xx"},
     'await action.verifyRequest("POST", "/api/x", "2xx");'),
    ({"action": "verifyRequest", "method": "POST", "urlPattern": "/api/x", "bodyContains": "alice"},
     'await action.verifyRequest("POST", "/api/x", undefined, undefined, "alice");'),
    ({"action": "verifyRequest", "method": "POST", "urlPattern": "/x", "status": 201, "message": "m"},
     'await action.verifyRequest("POST", "/x", 201, "m");'),
    ({"action": "verifyValidationMessage", "locator_key": "name", "value": "required"},
     'await action.verifyValidationMessage("name", "required");'),
    ({"action": "verifyAriaSnapshot", "locator_key": "list", "value": "- list:\n  - listitem: A"},
     'await action.verifyAriaSnapshot("list", "- list:\\n  - listitem: A");'),
    ({"action": "rememberCount", "locator_key": "row"}, 'await action.rememberCount("row");'),
    ({"action": "verifyCountChangedBy", "locator_key": "row", "delta": 0},
     'await action.verifyCountChangedBy("row", 0);'),
    ({"action": "verifyDownload", "locator_key": "export", "nameRegex": "\\.csv$", "minBytes": 10},
     'await action.verifyDownload("export", "\\\\.csv$", 10);'),
    ({"action": "verifyDownload", "locator_key": "export"}, 'await action.verifyDownload("export");'),
    ({"action": "verifyNewTab", "locator_key": "help_link", "urlContains": "/help"},
     'await action.verifyNewTab("help_link", "/help");'),
    ({"action": "verifyStorage", "store": "cookie", "key": "sid", "rule": "httpOnly"},
     'await action.verifyStorage("cookie", "sid", "httpOnly");'),
    ({"action": "verifyStorage", "store": "localStorage", "key": "cart", "rule": "contains", "value": "7"},
     'await action.verifyStorage("localStorage", "cart", "contains", "7");'),
    ({"action": "verifyResponseSchema", "urlPattern": "/api/p*", "schema": {"type": "object", "required": ["items"]}},
     'await action.verifyResponseSchema("/api/p*", {"type": "object", "required": ["items"]});'),
    ({"action": "verifyResponseSchema", "urlPattern": "/api/p*", "schemaRef": "test_creation/schemas/p.json"},
     'await action.verifyResponseSchema("/api/p*", "test_creation/schemas/p.json");'),
    ({"action": "verifyApiState", "url": "/api/products/7", "expect": {"status": 404, "junk": 1}},
     'await action.verifyApiState("GET", "/api/products/7", {"status": 404});'),
    ({"action": "mockRoute", "urlPattern": "/api/x", "status": 500, "body": {"e": 1}, "delayMs": 100},
     'await action.mockRoute("/api/x", {"status": 500, "body": {"e": 1}, "delayMs": 100});'),
    ({"action": "mockRoute", "urlPattern": "/slow"}, 'await action.mockRoute("/slow");'),
    ({"action": "setOffline", "value": True}, "await action.setOffline(true);"),
    ({"action": "setOffline", "value": False}, "await action.setOffline(false);"),
    ({"action": "setClock", "value": "2030-01-01T00:00:00Z"}, 'await action.setClock("2030-01-01T00:00:00Z");'),
]


@pytest.mark.parametrize("step,line", GOLDEN, ids=[f"{g[0]['action']}-{i}" for i, g in enumerate(GOLDEN)])
def test_renderer_golden(step, line):
    assert line in render([step], oracles=False)


def test_reload_and_verify_renders_reload_then_nested_verifies():
    step = {"action": "reloadAndVerify", "steps": [{"action": "verifyContainsText", "locator_key": "row", "value": "A"}]}
    out = render([step])
    assert 'await action.reload();\n    await action.verifyContainsText("row", "A");' in out
    stepped = render([step], test_steps=True)
    assert 'await test.step("1. Reload and verify: Verify \\"row\\" contains \\"A\\"", async () => {' in stepped
    assert '      await action.reload();\n      await action.verifyContainsText("row", "A");' in stepped


def test_step_titles_for_new_actions():
    assert step_title(2, {"action": "verifyCountChangedBy", "locator_key": "row", "delta": 1}) == \
        '2. Verify the count of "row" changed by 1'
    assert step_title(1, {"action": "setOffline", "value": True}) == "1. Go offline"
    assert "•••" in step_title(1, {"action": "verifyStorage", "store": "cookie", "key": "session_token",
                                    "rule": "equals", "value": "abc"})


# ── validation ────────────────────────────────────────────────────────────

def test_validation_accepts_every_new_action():
    validate([g[0] for g in GOLDEN if g[0]["action"] != "verifyCountChangedBy"]
             + [{"action": "verifyCountChangedBy", "locator_key": "row", "delta": 0},
                {"action": "reloadAndVerify", "steps": [{"action": "verifyVisible", "locator_key": "row"}]}])


@pytest.mark.parametrize("steps,why", [
    ([{"action": "verifyCountChangedBy", "locator_key": "row", "delta": 1}], "rememberCount"),
    ([{"action": "rememberCount", "locator_key": "row"},
      {"action": "verifyCountChangedBy", "locator_key": "row", "delta": "1"}], "integer"),
    ([{"action": "reloadAndVerify", "steps": [{"action": "click", "locator_key": "save"}]}], "verify"),
    ([{"action": "reloadAndVerify", "steps": []}], "non-empty"),
    ([{"action": "verifyStorage", "store": "indexedDb", "key": "x", "rule": "present"}], "store"),
    ([{"action": "verifyStorage", "store": "cookie", "key": "x", "rule": "equals"}], "value"),
    ([{"action": "verifyResponseSchema", "urlPattern": "/x"}], "schema"),
    ([{"action": "verifyApiState", "url": "/x", "expect": "200"}], "object"),
    ([{"action": "verifyNewTab", "locator_key": "help_link"}], "urlContains"),
    ([{"action": "verifyValidationMessage", "locator_key": "name"}], "value"),
    ([{"action": "verifyDownload", "locator_key": "nope"}], "disallowed locator_key"),
])
def test_validation_rejects(steps, why):
    with pytest.raises(LLMResponseValidationError, match=why):
        validate(steps)


# ── linter rule table (good + bad per rule) ─────────────────────────────────

FILL = {"action": "enterText", "locator_key": "name", "value": "Lamp"}
SAVE = {"action": "click", "locator_key": "save"}
OK_REQ = {"action": "verifyRequest", "method": "POST", "urlPattern": "/products", "status": "2xx"}
UI_OK = {"action": "verifyContainsText", "locator_key": "msg", "value": "Product created"}
ERR = {"action": "verifyContainsText", "locator_key": "err", "value": "Name is required"}
NOREQ = {"action": "verifyNoRequest", "method": "POST", "urlPattern": "/products"}
XSS = {"action": "enterText", "locator_key": "q", "value": "<img src=x onerror=alert(1)>"}

LINT = [
    # (test, weak?, issue prefix)
    (T([FILL, SAVE, UI_OK, OK_REQ]), False, None),
    (T([FILL, SAVE, UI_OK]), True, "submit: a positive submit needs backend"),
    (T([FILL, SAVE, OK_REQ]), True, "submit: a positive submit needs a UI"),
    (T([FILL, SAVE, UI_OK, {**OK_REQ, "status": 400}]), True, "submit"),
    (T([FILL, SAVE, UI_OK, {**OK_REQ, "status": 201}]), False, None),
    (T([FILL, SAVE, UI_OK, {"action": "reloadAndVerify", "steps": [UI_OK]}]), False, None),
    (T([FILL, SAVE, UI_OK, {"action": "verifyApiState", "url": "/api/p", "expect": {"status": 200}}]), False, None),
    (T([{"action": "rememberCount", "locator_key": "row"}, FILL, SAVE, UI_OK,
        {"action": "verifyCountChangedBy", "locator_key": "row", "delta": 1}]), False, None),
    (T([{"action": "enterText", "locator_key": "search_box", "value": "lamp"}, {"action": "click", "locator_key": "go"},
        {"action": "verifyContainsText", "locator_key": "row", "value": "Lamp"}]), False, None),   # search: not a submit
    (T([FILL, SAVE, ERR, NOREQ], "negative"), False, None),
    (T([FILL, SAVE, {"action": "verifyValidationMessage", "locator_key": "name", "value": "fill"}, NOREQ], "negative"),
     False, None),
    (T([{"action": "rememberCount", "locator_key": "row"}, FILL, SAVE, ERR,
        {"action": "verifyCountChangedBy", "locator_key": "row", "delta": 0}], "negative"), False, None),
    (T([{"action": "rememberCount", "locator_key": "row"}, FILL, SAVE, ERR,
        {"action": "verifyCountChangedBy", "locator_key": "row", "delta": 1}], "negative"), True, "negative: needs verifyNoRequest"),
    (T([FILL, SAVE, NOREQ], "negative"), True, "negative: needs error text"),
    (T([FILL, SAVE, {"action": "verifyVisible", "locator_key": "save"}], "negative"), True, "outcome"),
    (T([XSS, {"action": "click", "locator_key": "go"}, {"action": "verifyNoDialog"},
        {"action": "verifyNotInjected", "payloadMarker": "onerror=alert(1)"}]), False, None),
    (T([XSS, {"action": "click", "locator_key": "go"}, {"action": "verifyNoDialog"}]), True, "xss"),
    (T([{"action": "navigate"}, {"action": "verifyTitle", "value": "Shop"}]), True, "title"),
    (T([{"action": "navigate"}, {"action": "verifyStorage", "store": "cookie", "key": "sid", "rule": "httpOnly"}]),
     False, None),
    (T([{"action": "click", "locator_key": "export"}, {"action": "verifyVisible", "locator_key": "export"}]), True, "outcome"),
    (T([{"action": "verifyDownload", "locator_key": "export", "nameRegex": "csv"}]), False, None),
]


@pytest.mark.parametrize("test,weak,issue", LINT, ids=[f"lint-{i}" for i in range(len(LINT))])
def test_linter_rules(test, weak, issue):
    r = L.lint_test(test)
    assert r["weak"] is weak, r
    if issue:
        assert any(i.startswith(issue) for i in r["issues"]), r["issues"]


def test_linter_counts_reload_and_verify_steps_as_assertions():
    t = T([SAVE, {"action": "reloadAndVerify", "steps": [{"action": "verifyContainsText", "locator_key": "row",
                                                         "value": "x"}]}])
    assert not L.lint_test(t)["weak"]


# ── 5.4 oracles from test_cases.json ───────────────────────────────────────

CASE = {
    "id": "TC-1", "title": "empty name is rejected", "test_type": "negative",
    "target": {"kind": "form", "sample_url": "http://127.0.0.1:8765/products/new", "field": "name"},
    "locator_keys": {"name": "name", "submit": "save"},
    "oracles": [{"type": "field_invalid", "field": "name"},
                {"type": "error_text", "contains": "Name is required", "source": "brd"},
                {"type": "no_request", "method": "post", "url": "http://127.0.0.1:8765/products", "source": "observed"},
                {"type": "url_unchanged", "source": "observed"}],
}


def test_case_oracles_fill_placeholder_and_append_missing_checks():
    plan = {"tests": [{"name": "empty name", "type": "negative", "case_id": "TC-1",
                       "steps": [{"action": "click", "locator_key": "save"},
                                 {"action": "verifyText", "locator_key": "err", "value": ""}]}]}
    out = sg._reconcile_design_plan(plan, [CASE], oracles=True)
    steps = out["tests"][0]["steps"]
    assert steps[1] == {"action": "verifyContainsText", "locator_key": "err", "value": "Name is required"}
    added = {s["action"]: s for s in steps[2:]}
    assert added["verifyFieldInvalid"]["locator_key"] == "name"
    assert added["verifyNoRequest"] == {"action": "verifyNoRequest", "method": "POST", "urlPattern": "/products",
                                        "message": "oracle from TC-1"}
    assert added["verifyUrlContains"]["value"] == "/products/new"
    assert not L.lint_test(out["tests"][0])["weak"]


def test_case_oracles_off_without_flag_and_placeholder_without_message_still_dropped():
    plan = {"tests": [{"name": "empty name", "type": "negative", "case_id": "TC-1",
                       "steps": [SAVE, {"action": "verifyText", "locator_key": "err", "value": ""}]}]}
    off = sg._reconcile_design_plan(plan, [CASE])                       # flag off: Phase 3 behaviour, dropped
    assert not off["tests"] and off["dropped_tests"][0]["reason"] == "placeholder_negative_dropped"
    no_msg = {**CASE, "oracles": [{"type": "no_request", "method": "POST", "url": "/products"}]}
    out = sg._reconcile_design_plan(plan, [no_msg], oracles=True)
    assert not out["tests"] and out["dropped_tests"][0]["reason"] == "placeholder_negative_dropped"


def test_placeholder_negative_kept_when_its_design_case_has_a_rejection_oracle():
    plan = {"tests": [{"name": "empty name", "type": "negative", "case_id": "TC-1",
                       "steps": [SAVE, {"action": "verifyText", "locator_key": "err", "value": ""}]}]}
    kept, dropped = sg._drop_placeholder_negative_tests(plan, {}, [CASE])
    assert not dropped and kept["tests"]
    _, dropped = sg._drop_placeholder_negative_tests(plan, {}, [])
    assert dropped == ["empty name"]


def test_llm_inferred_oracle_marked_low_confidence():
    case = {**CASE, "test_type": "positive", "oracles": [{"type": "outcome", "expected": "x", "source": "llm_inferred"}]}
    plan = {"tests": [{"name": "t", "type": "positive", "case_id": "TC-1", "steps": [UI_OK]}]}
    assert sg._reconcile_design_plan(plan, [case], oracles=True)["tests"][0]["oracle_confidence"] == "low"
    assert "oracle_confidence" not in sg._reconcile_design_plan(plan, [CASE | {"test_type": "positive"}],
                                                                oracles=True)["tests"][0]


# ── 5.2 conflicts → review queue + report ───────────────────────────────────

CONFLICT = {"ac_id": "AC-3.1", "form_id": "F1", "field": "name", "probe": "empty", "brd": "Name is required",
            "observed": "accepted (empty)"}


def test_conflicts_queued_once(tmp_path):
    assert flag_expected_value_conflicts("p", [CONFLICT], output_dir=str(tmp_path)) == 1
    assert flag_expected_value_conflicts("p", [CONFLICT], output_dir=str(tmp_path)) == 0
    queue = json.loads((tmp_path / "human_review_queue.json").read_text(encoding="utf-8"))
    assert [e["kind"] for e in queue] == ["expected_value_conflict"]


def test_report_lists_potential_defects_and_low_confidence():
    plans = {"plans": {"S": {"tests": [{"name": "a", "oracle_confidence": "low"}, {"name": "b"}]}}}
    s = qs.compute_summary([], None, plans, {}, None, None, {"conflicts": [CONFLICT]})
    assert s["potential_defects"] == 1 and s["low_confidence_oracles"] == 1
    assert qs.potential_defects({"conflicts": [CONFLICT]})[0]["observed"] == "accepted (empty)"
    from tools.test_execution.reports.html_report import _quality_sections
    html = _quality_sections({"summary": s, "gates": {}, "potential_defects": qs.potential_defects({"conflicts": [CONFLICT]})})
    assert "Potential defects — BRD vs observed" in html and "accepted (empty)" in html
