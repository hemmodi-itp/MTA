"""Phase 5-lean: assertion linter rules (good + bad plan each) and renderer output for the oracle actions."""
from agents.test_creation.script_generation.agent import ALLOWED_ACTIONS, _validate_plan
from agents.common.failure_classifier import LLMResponseValidationError
from tools.test_creation import assertion_linter as L
from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan
import pytest


def T(steps, type="positive", **kw):
    return {"name": "t", "type": type, "steps": steps, **kw}


def test_outcome_good_and_bad():
    bad = T([{"action": "click", "locator_key": "go"}, {"action": "verifyVisible", "locator_key": "go"}])
    good = T([{"action": "click", "locator_key": "go"}, {"action": "verifyUrlContains", "value": "/done"}])
    assert L.lint_test(bad)["weak"] and "outcome" in L.lint_test(bad)["issues"][0]
    assert not L.lint_test(good)["weak"]


def test_title_only_rejected_unless_smoke_reachability():
    steps = [{"action": "navigate"}, {"action": "verifyTitleContains", "value": "Shop"}]
    assert L.lint_test(T(steps))["score"] == 0
    assert not L.lint_test(T(steps, technique="smoke-reachability"))["weak"]


NEG_OK = [{"action": "click", "locator_key": "save"}, {"action": "verifyContainsText", "locator_key": "err", "value": "x"},
          {"action": "verifyNoRequest", "method": "POST", "urlPattern": "/api/save"}]


def test_negative_needs_error_and_no_submit():
    assert not L.lint_test(T(NEG_OK, "negative"))["weak"]
    only_err = NEG_OK[:2]
    assert L.lint_test(T(only_err, "negative"))["weak"]
    only_nosubmit = [NEG_OK[0], NEG_OK[2]]
    assert L.lint_test(T(only_nosubmit, "negative"))["weak"]
    invalid_url = [NEG_OK[0], {"action": "verifyFieldInvalid", "locator_key": "email"},
                   {"action": "verifyUrlContains", "value": "/form"}]
    assert not L.lint_test(T(invalid_url, "negative"))["weak"]


def test_xss_needs_dialog_and_not_injected():
    base = [{"action": "enterText", "locator_key": "q", "value": "<script>alert(1)</script>"},
            {"action": "click", "locator_key": "go"}, {"action": "verifyContainsText", "locator_key": "res", "value": "x"}]
    assert L.lint_test(T(base))["weak"]
    full = base + [{"action": "verifyNoDialog"}, {"action": "verifyNotInjected", "payloadMarker": "alert(1)"}]
    assert not L.lint_test(T(full))["weak"]
    assert L.lint_test(T(base + [{"action": "verifyNoDialog"}], technique="special_chars"))["weak"]


def test_wait_for_timeout_rejected():
    r = L.lint_test(T([{"action": "waitForTimeout", "value": 500}, {"action": "verifyUrlContains", "value": "/a"}]))
    assert r["score"] == 0 and r["issues"][0].startswith("sleep")


def test_plan_report_and_feedback():
    rep = L.lint_plan({"tests": [T(NEG_OK, "negative"), T([{"action": "navigate"}])]})
    assert len(rep["weak"]) == 1 and "test" in L.feedback(rep["weak"])


def test_validate_requires_oracle_fields():
    ok = {"tests": [T([{"action": "verifyNoRequest", "method": "POST", "urlPattern": "/a"}])]}
    _validate_plan(ok, "S", ALLOWED_ACTIONS, set(), {})
    with pytest.raises(LLMResponseValidationError):
        _validate_plan({"tests": [T([{"action": "verifyRequest", "method": "POST"}])]}, "S", ALLOWED_ACTIONS, set(), {})


def _render(steps, oracles=True):
    plan = {"tests": [T(steps)]}
    return render_spec_from_plan(plan, {"scenario_id": "S"}, "", "projects/p/test_creation/test_scripts/M/a.spec.ts",
                                 oracles=oracles)


def test_renderer_new_actions():
    out = _render([
        {"action": "verifyRequest", "method": "post", "urlPattern": "/api/x", "status": 201},
        {"action": "verifyRequest", "method": "GET", "urlPattern": "/api/y"},
        {"action": "verifyNoRequest", "method": "POST", "urlPattern": "/api/z"},
        {"action": "verifyFieldInvalid", "locator_key": "email"},
        {"action": "verifyNoDialog"},
        {"action": "verifyNotInjected", "payloadMarker": "alert(1)"},
    ])
    for line in ['action.verifyRequest("POST", "/api/x", 201);', 'action.verifyRequest("GET", "/api/y");',
                 'action.verifyNoRequest("POST", "/api/z");', 'action.verifyFieldInvalid("email");',
                 'action.verifyNoDialog();', 'action.verifyNotInjected("alert(1)");']:
        assert line in out
    assert out.rstrip().splitlines()[-4].strip() == "await action.verifyNoNewConsoleErrors();"


def test_renderer_console_check_only_with_flag():
    assert "verifyNoNewConsoleErrors" not in _render([{"action": "navigate"}], oracles=False)
