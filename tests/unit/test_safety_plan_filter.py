"""Phase 0.5 — plan filter, payload detector, test-data filter, and the
acceptance criterion: a generated step that clicks "Delete account" is dropped
when allow_destructive is false (through ScriptGenerationAgent.execute)."""

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools.safety.payloads import detect_payload
from tools.safety.plan_filter import filter_plan
from tools.safety.policy import SafetyPolicy
from tools.safety.testdata_filter import drop_security_payloads
from tools.test_creation.testdata.models import (
    NegativeVariant,
    ScenarioTestData,
    TestDataField,
    TestDataIteration,
)

LOCATOR_MAP = {
    "delete_account_btn": {"type": "role", "locator": "button", "name": "Delete account"},
    "profile_link": {"type": "role", "locator": "link", "name": "Profile"},
    "confirm_dialog_heading": {"type": "text", "locator": "Are you sure?"},
}

PLAN = {
    "tests": [
        {"name": "positive — open profile", "type": "positive", "steps": [
            {"action": "navigate"},
            {"action": "click", "locator_key": "profile_link"},
            {"action": "verifyUrlContains", "value": "/profile", "message": "on profile"},
        ]},
        {"name": "positive — delete account", "type": "positive", "steps": [
            {"action": "navigate"},
            {"action": "click", "locator_key": "delete_account_btn"},
            {"action": "verifyVisible", "locator_key": "confirm_dialog_heading", "message": "asks"},
        ]},
    ],
    "missing_actions": [],
    "missing_locators": [],
}


def _policy(**kw):
    raw = {"environment": kw.pop("environment", "local"),
           "safety": {"allow_destructive": kw.pop("allow_destructive", False),
                      "allowed_hosts": kw.pop("allowed_hosts", ["app.test"])}}
    return SafetyPolicy.from_project_config(raw)


def test_destructive_test_dropped_whole_and_reported():
    out, dropped = filter_plan(PLAN, _policy(), LOCATOR_MAP)
    assert [t["name"] for t in out["tests"]] == ["positive — open profile"]
    assert len(dropped) == 1
    d = dropped[0]
    assert d["test"] == "positive — delete account"
    assert d["reason"] == "destructive_action"
    assert d["category"] == "delete"
    assert d["step_index"] == 1 and d["locator_key"] == "delete_account_btn"
    assert out["dropped_for_safety"] == dropped
    assert out["missing_actions"] == [] and "tests" in PLAN and len(PLAN["tests"]) == 2  # input not mutated


def test_destructive_kept_when_allowed_on_non_prod():
    out, dropped = filter_plan(PLAN, _policy(allow_destructive=True), LOCATOR_MAP)
    assert len(out["tests"]) == 2 and dropped == []


def test_destructive_dropped_on_prod_even_if_allowed():
    out, dropped = filter_plan(PLAN, _policy(environment="prod", allow_destructive=True), LOCATOR_MAP)
    assert len(out["tests"]) == 1 and len(dropped) == 1


def test_destructive_step_inside_flow_is_caught():
    plan = {"tests": [{"name": "uses flow", "type": "positive", "steps": [
        {"action": "useFlow", "flow": "wipe_profile", "args": {}},
    ]}]}
    flows = {"wipe_profile": {"params": [], "steps": [
        {"action": "click", "locator_key": "delete_account_btn"},
    ]}}
    out, dropped = filter_plan(plan, _policy(), LOCATOR_MAP, flows)
    assert out["tests"] == []
    assert dropped[0]["flow"] == "wipe_profile"


def test_navigation_outside_allowed_hosts_dropped_even_when_destructive_allowed():
    plan = {"tests": [{"name": "leaves site", "type": "positive", "steps": [
        {"action": "navigate", "value": "https://evil.example.com/"},
    ]}, {"name": "stays", "type": "positive", "steps": [
        {"action": "navigate", "value": "https://app.test/home"},
        {"action": "navigate", "value": "/relative"},
    ]}]}
    out, dropped = filter_plan(plan, _policy(allow_destructive=True), {})
    assert [t["name"] for t in out["tests"]] == ["stays"]
    assert dropped[0]["reason"] == "host_not_allowed"


@pytest.mark.parametrize("value,category", [
    ("<script>alert(1)</script>", "xss"),
    ('"><img src=x onerror=alert(1)>', "xss"),
    ("javascript:alert(document.cookie)", "xss"),
    ("' OR '1'='1", "sqli"),
    ("1 UNION SELECT password FROM users", "sqli"),
    ("x'; DROP TABLE users; --", "sqli"),
    ('{"$ne": null}', "nosqli"),
    ("../../../../etc/passwd", "path_traversal"),
    ("{{7*7}}", "template_injection"),
    ("; cat /etc/passwd", "command_injection"),
])
def test_payload_detector_hits(value, category):
    assert detect_payload(value) == category


@pytest.mark.parametrize("value", [
    "O'Brien", "alice@example.com", "Rock & Roll", "a" * 300, "50% off", "x < y", "", None, 42,
    "Select the best option", "Drop-off point",
])
def test_payload_detector_ignores_ordinary_values(value):
    assert detect_payload(value) is None


def _dataset():
    f = lambda n, v: TestDataField(field_name=n, field_type="text", value=v)  # noqa: E731
    return ScenarioTestData(
        testdata_id="TD-001", scenario_id="BS-001", scenario_title="t", actor="user",
        positive_dataset=[f("name", "Widget")],
        negative_variants=[
            NegativeVariant(variant_id="NEG-001", variant_type="negative", description="xss + empty",
                            iterations=[TestDataIteration(fields=[f("name", "<script>alert(1)</script>")], expected_error="bad"),
                                        TestDataIteration(fields=[f("name", "")], expected_error="Name is required")]),
            NegativeVariant(variant_id="NEG-002", variant_type="negative", description="sqli only",
                            iterations=[TestDataIteration(fields=[f("name", "' OR '1'='1")], expected_error="bad")]),
            NegativeVariant(variant_id="NEG-003", variant_type="boundary", description="long",
                            iterations=[TestDataIteration(fields=[f("name", "a" * 51)], expected_error="too long")]),
        ],
    )


def test_testdata_payload_iterations_and_empty_variants_removed():
    original = _dataset()
    (out,), dropped = drop_security_payloads([original])
    ids = [v.variant_id for v in out.negative_variants]
    assert ids == ["NEG-001", "NEG-003"]
    assert len(out.negative_variants[0].iterations) == 1
    assert out.negative_variants[0].iterations[0].fields[0].value == ""
    reasons = [(d.get("variant_id"), d.get("scope")) for d in dropped]
    assert ("NEG-002", "variant") in reasons
    assert len(original.negative_variants) == 3  # not mutated


def test_testdata_clean_dataset_returned_unchanged():
    ds = SimpleNamespace(scenario_id="S", positive_dataset=[], negative_variants=[])
    out, dropped = drop_security_payloads([ds])
    assert out[0] is ds and dropped == []


# ── Acceptance: ScriptGenerationAgent.execute drops the "Delete account" test ──

_LLM_PLAN = json.dumps(PLAN)


class _StubLLM:
    def generate(self, prompt: str) -> str:
        return _LLM_PLAN


def _setup_project(tmp_path, safety_block):
    import yaml

    proj = tmp_path / "proj"
    (proj / "test_comprehension").mkdir(parents=True)
    (proj / "test_creation").mkdir()
    (proj / "test_comprehension" / "business_scenarios.json").write_text(json.dumps({"scenarios": [
        {"scenario_id": "BS-001", "title": "Manage account", "module_id": "M01"}]}), encoding="utf-8")
    (proj / "test_creation" / "locator_map.json").write_text(json.dumps(
        {k: {**v, "_module_id": "M01", "_source_locator_id": f"LOC-{i}"} for i, (k, v) in enumerate(LOCATOR_MAP.items())}
    ), encoding="utf-8")
    (proj / "test_creation" / "scenario_element_map.json").write_text(json.dumps({"BS-001": {
        "scenario_title": "Manage account",
        "relevant_elements": [{"locator_id": f"LOC-{i}"} for i in range(len(LOCATOR_MAP))]}}), encoding="utf-8")
    (proj / "project.yaml").write_text(yaml.safe_dump({
        "project": {"name": "proj"}, **safety_block,
        "modules": [{"id": "M01", "url": "https://app.test/account"}]}), encoding="utf-8")
    return proj


def _run_agent(tmp_path, monkeypatch, safety_block):
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent

    proj = _setup_project(tmp_path, safety_block)
    monkeypatch.setattr("agents.test_creation.script_generation.agent._ASSETS_BASE", str(tmp_path))
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    agent = ScriptGenerationAgent(settings={})
    agent._registry.get_llm = MagicMock(return_value=_StubLLM())
    with patch.object(ScriptGenerationAgent, "_validate_locator_map_live", return_value=set()), \
         patch("agents.test_creation.script_generation.agent.write_named_locator_map",
               return_value={"added": [], "updated": [], "possibly_removed": []}), \
         patch("agents.test_creation.script_generation.agent.update_catalog"):
        out = agent.execute({"project_name": "proj",
                             "modules": [{"id": "M01", "url": "https://app.test/account"}]}, {})
    return proj, out


def test_acceptance_delete_account_step_dropped_by_default(tmp_path, monkeypatch):
    proj, out = _run_agent(tmp_path, monkeypatch, {})  # no environment, no safety block
    assert out["scripts_generated"] == 1
    spec_dir = proj / "test_creation" / "test_scripts" / "M01"
    spec = next(spec_dir.glob("*.spec.ts")).read_text(encoding="utf-8")
    assert "delete_account_btn" not in spec
    assert "profile_link" in spec
    assert 'test.use({ baseURL: "https://app.test/account" });' in spec
    from contracts.artifacts import load_payload

    raw = json.loads((proj / "test_creation" / "test_plans.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2  # written as a v2 envelope
    plans = load_payload("test_plans", str(proj / "test_creation" / "test_plans.json"))
    assert plans["BS-001"]["dropped_for_safety"][0]["test"] == "positive — delete account"
    queue = json.loads((proj / "human_review_queue.json").read_text(encoding="utf-8"))
    assert any(e["kind"] == "safety_drop" and e["environment"] == "unspecified" for e in queue)


def test_acceptance_delete_account_kept_when_allowed_on_local(tmp_path, monkeypatch):
    proj, out = _run_agent(tmp_path, monkeypatch,
                           {"environment": "local", "safety": {"allow_destructive": True}})
    spec = next((proj / "test_creation" / "test_scripts" / "M01").glob("*.spec.ts")).read_text(encoding="utf-8")
    assert "delete_account_btn" in spec
