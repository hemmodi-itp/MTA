"""Phase 4.6 — no fixed sleeps in LLM-generated plans; human-authored flows keep waitForTimeout."""

import pytest

from agents.common.failure_classifier import LLMResponseValidationError
from agents.test_creation.script_generation.agent import ALLOWED_ACTIONS, FIXED_SLEEP_ACTIONS, _validate_plan
from agents.test_creation.script_generation.prompt import ACTION_LIBRARY_PROMPT
from tools.test_creation.script_generator.spec_renderer import render_flows_module


def _plan(*steps):
    return {"tests": [{"name": "t", "steps": list(steps)}], "missing_actions": [], "missing_locators": []}


def test_wait_for_timeout_is_not_in_the_llm_vocabulary():
    assert "waitForTimeout" not in ALLOWED_ACTIONS
    assert "waitForTimeout" in FIXED_SLEEP_ACTIONS
    assert "waitForElement" in ALLOWED_ACTIONS
    assert '"waitForTimeout"' not in getattr(ACTION_LIBRARY_PROMPT, "template", ACTION_LIBRARY_PROMPT)


def test_validator_rejects_wait_for_timeout_with_a_specific_message():
    plan = _plan({"action": "click", "locator_key": "go"}, {"action": "waitForTimeout", "value": 500})
    with pytest.raises(LLMResponseValidationError, match="fixed sleeps are not allowed in generated plans"):
        _validate_plan(plan, "M01_BS_001", ALLOWED_ACTIONS, {"go"}, {})


def test_validator_rejects_it_even_if_a_caller_passes_it_as_allowed():
    plan = _plan({"action": "waitForTimeout", "value": 500})
    with pytest.raises(LLMResponseValidationError, match="waitForTimeout"):
        _validate_plan(plan, "M01_BS_001", ALLOWED_ACTIONS | {"waitForTimeout"}, set(), {})


def test_web_first_wait_is_still_valid():
    _validate_plan(_plan({"action": "waitForElement", "locator_key": "toast", "value": "visible"}),
                   "M01_BS_001", ALLOWED_ACTIONS, {"toast"}, {})


def test_human_authored_flows_still_render_wait_for_timeout():
    ts = render_flows_module({"settle": {"params": [], "steps": [{"action": "waitForTimeout", "value": 300}]}}, "shop")
    assert "await action.waitForTimeout(300);" in ts
