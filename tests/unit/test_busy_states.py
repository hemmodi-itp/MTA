"""'Disabled while saving' is checked while the save is in flight (tools/test_creation/busy_states.py)."""

from agents.test_creation.script_generation.agent import ALLOWED_ACTIONS, _validate_plan
from tools.test_creation.assertion_linter import lint_plan
from tools.test_creation.busy_states import ground_busy_states
from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan


def _plan(click="click", key2="save"):
    return {"tests": [{"name": "save is disabled while saving", "type": "positive", "steps": [
        {"action": "navigate", "value": "/products/new"},
        {"action": "enterText", "locator_key": "name", "value": "Desk"},
        {"action": click, "locator_key": "save"},
        {"action": "verifyDisabled", "locator_key": key2, "message": "Save is disabled while saving"},
        {"action": "verifyUrlContains", "value": "/products/"}]}]}


def test_click_then_verify_disabled_becomes_one_busy_check():
    for click in ("click", "doubleClick"):
        out, changes = ground_busy_states(_plan(click))
        steps = out["tests"][0]["steps"]
        assert [s["action"] for s in steps] == ["navigate", "enterText", "verifyBusyWhileSubmitting", "verifyUrlContains"]
        assert steps[2] == {"action": "verifyBusyWhileSubmitting", "locator_key": "save",
                            "message": "Save is disabled while saving"}
        assert changes[0]["change"] == "busy state"


def test_other_elements_are_left_alone():
    assert ground_busy_states(_plan(key2="other"))[1] == []


def test_the_action_is_allowed_rendered_and_counts_as_an_outcome():
    plan, _ = ground_busy_states(_plan())
    assert "verifyBusyWhileSubmitting" in ALLOWED_ACTIONS
    _validate_plan(plan, "S1", ALLOWED_ACTIONS, {"name", "save"}, {})
    ts = render_spec_from_plan(plan, {"scenario_id": "M03_BS_003", "title": "t"}, "http://h",
                               "projects/p/test_creation/test_scripts/M03/t.spec.ts")
    assert 'await action.verifyBusyWhileSubmitting("save", "Save is disabled while saving");' in ts
    assert not any("outcome" in i for i in lint_plan(plan)["results"][0]["issues"])
