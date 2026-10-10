"""Phase 1.3 — Playwright tags / annotations on generated tests: the details object on the header line, the AC
title prefix, byte-identical output for untraced plans, compatibility with healing's block extraction, the
Python-fallback describe tags, and PlanTracer's annotation of plan tests."""


import pytest

from agents.common.fallback_core import fallback_generate_script
from agents.test_execution.healing.tools import _extract_test_block
from tools.requirements.models import RequirementsDoc
from tools.requirements.tracing import PlanTracer, record_drops
from tools.state.artifact_registry import ArtifactRegistry
from tools.test_creation.script_generator.spec_renderer import (
    render_spec_from_plan,
    render_test_details,
    render_test_title,
)

SCENARIO = {"scenario_id": "M01_BS_002", "title": "Failed login", "module_id": "M01"}
REL = "projects/demo/test_creation/test_scripts/M01/test_M01_BS_002_failed_login.spec.ts"
STEPS = [{"action": "enterText", "locator_key": "password", "value": "nope"},
         {"action": "click", "locator_key": "login_button"},
         {"action": "verifyContainsText", "locator_key": "error", "value": "Invalid username or password",
          "message": "generic error"}]
TRACED = {"name": "negative — wrong password shows a generic error", "type": "negative", "steps": STEPS,
          "tc_id": "M01_TC_002", "ac_ids": ["AC-01.2"], "ac_link": "direct", "req_ids": ["REQ-01"],
          "priority": "P1"}


def _plan(*tests):
    return {"tests": list(tests), "missing_actions": [], "missing_locators": []}


def test_traced_test_header_is_one_line_with_tags_and_annotations():
    out = render_spec_from_plan(_plan(TRACED), SCENARIO, "https://shop.test/login", REL)
    header = next(ln for ln in out.splitlines() if ln.strip().startswith("test("))
    assert header == (
        '  test("AC-01.2 negative — wrong password shows a generic error", { tag: ["@P1", "@negative", '
        '"@regression", "@REQ-01", "@AC-01.2"], annotation: [{ type: "ac", description: "AC-01.2" }, '
        '{ type: "tc", description: "M01_TC_002" }, { type: "scenario", description: "M01_BS_002" }] }, '
        'async ({ action }) => {')
    assert "@regression\"" not in header.split(",")[0]         # the tag moved out of the title


def test_inherited_and_similarity_links_are_annotated():
    t = {**TRACED, "ac_link": "inherited", "ac_ids": ["AC-01.1", "AC-01.2"]}
    details = render_test_details(t, "M01_BS_002")
    assert '{ type: "ac_link", description: "inherited" }' in details
    assert details.count('type: "ac"') == 2 and '"@AC-01.1", "@AC-01.2"' in details


def test_unlinked_traced_test_has_no_ac_prefix_or_ac_tags():
    t = {**TRACED, "ac_ids": [], "ac_link": None, "req_ids": [], "priority": None}
    assert render_test_title(t) == t["name"]
    assert render_test_details(t, "") == ('{ tag: ["@negative", "@regression"], annotation: '
                                          '[{ type: "tc", description: "M01_TC_002" }] }')


def test_title_prefix_not_repeated():
    assert render_test_title({**TRACED, "name": "AC-01.2 wrong password"}) == "AC-01.2 wrong password"


def test_healing_block_extraction_still_works_on_traced_tests():
    out = render_spec_from_plan(_plan(TRACED, {**TRACED, "name": "positive — ok", "type": "positive",
                                               "tc_id": "M01_TC_003"}), SCENARIO, "https://shop.test", REL)
    block = _extract_test_block(out, render_test_title(TRACED))
    assert block.lstrip().startswith('test("AC-01.2 negative')
    assert block.rstrip().endswith("});") and "M01_TC_003" not in block
    assert 'await action.click("login_button");' in block


# Golden output of the Phase 0 renderer (commit 2bf04b6) for the plan below — captured before Phase 1 changed
# spec_renderer.py. Untraced plans (requirements.enabled off → no tc_id) must still render exactly this.
_PHASE0_GOLDEN = (
    "// Base URL (from project.yaml, resolved via playwright.config.ts): https://shop.test/login\n"
    "import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';\n\n"
    'test.use({ baseURL: "https://shop.test/login" });\n\n'
    'test.describe("Failed login (M01_BS_002)", () => {\n\n'
    '  test("positive — logs in @smoke", async ({ action }) => {\n'
    '    await action.enterText("password", "nope");\n'
    '    await action.click("login_button");\n'
    "  });\n\n"
    '  test("negative — wrong password @regression", async ({ action }) => {\n'
    '    await action.enterText("password", "nope");\n'
    '    await action.click("login_button");\n'
    '    await action.verifyContainsText("error", "Invalid username or password", "generic error");\n'
    "  });\n\n"
    "});\n"
)


def test_untraced_output_is_byte_identical_to_the_phase0_renderer():
    untraced = {"name": "negative — wrong password", "type": "negative", "steps": STEPS}
    positive = {"name": "positive — logs in", "type": "positive", "steps": STEPS[:2]}
    assert render_spec_from_plan(_plan(positive, untraced), SCENARIO, "https://shop.test/login", REL) == _PHASE0_GOLDEN


def test_fallback_spec_describe_is_tagged_only_when_linked():
    linked = fallback_generate_script({**SCENARIO, "steps": ["a"], "ac_ids": ["AC-01.2"]}, [], None, "https://x.test")
    plain = fallback_generate_script({**SCENARIO, "steps": ["a"]}, [], None, "https://x.test")
    assert ('{ tag: ["@degraded", "@AC-01.2"], annotation: [{ type: "degraded", description: '
            '"python fallback - not counted as coverage" }] }, () => {') in linked
    assert "test.describe('Failed login (M01_BS_002) [degraded fallback]', () => {" in plain


# ── PlanTracer ───────────────────────────────────────────────────────────────

def _doc():
    ac = lambda i, s, p="P2", **kw: {"id": i, "statement": s, "testability": "ui", "testability_reason": "r",
                                     "priority": p, **kw}
    return RequirementsDoc.model_validate({"requirements": [{"id": "REQ-01", "title": "Login", "module_id": "M01",
        "acceptance_criteria": [ac("AC-01.1", "valid credentials land on the Products page", "P0"),
                                ac("AC-01.2", "a wrong password shows Invalid username or password", "P1")]}]})


def test_plan_tracer_annotates_tests(tmp_path):
    tracer = PlanTracer("p", _doc(), registry=ArtifactRegistry(str(tmp_path)))
    scenario = {**SCENARIO, "ac_ids": ["AC-01.1", "AC-01.2"]}
    plan = _plan({"name": "negative — wrong password", "type": "negative", "steps": STEPS, "ac_ids": ["AC-01.2"]},
                 {"name": "positive — happy path", "type": "positive", "steps": []},
                 {"name": "negative — bogus", "type": "negative", "steps": [], "ac_ids": ["AC-99.1"]})
    out = tracer.annotate(plan, scenario, "M01")
    a, b, c = out["tests"]
    assert (a["tc_id"], a["ac_ids"], a["ac_link"], a["priority"], a["req_ids"]) == (
        "M01_TC_001", ["AC-01.2"], "direct", "P1", ["REQ-01"])
    assert a["title"] == "AC-01.2 negative — wrong password"
    assert (b["ac_link"], b["ac_ids"], b["priority"]) == ("inherited", ["AC-01.1", "AC-01.2"], "P0")
    assert c["ac_ids"] == ["AC-01.1", "AC-01.2"] and c["ac_link"] == "inherited"   # unknown id dropped
    assert "tc_id" not in plan["tests"][0]                                           # input not mutated


def test_plan_tracer_prompt_block(tmp_path):
    tracer = PlanTracer("p", _doc(), registry=ArtifactRegistry(str(tmp_path)))
    block = tracer.prompt_block({**SCENARIO, "ac_ids": ["AC-01.2"]})
    assert "- AC-01.2: a wrong password shows Invalid username or password" in block
    assert '"ac_ids"' in block
    assert tracer.prompt_block(SCENARIO) == ""


def test_plan_tracer_disabled_or_missing_requirements(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "project.yaml").write_text("requirements:\n  enabled: true\n", encoding="utf-8")
    assert PlanTracer.for_project("p") is None                        # enabled, but no requirements.json
    assert PlanTracer.for_project("p", {"requirements": {"enabled": False}}) is None


def test_record_drops():
    plan = record_drops({"tests": []}, ["negative — empty"], ["negative — x: enterText('btn') — 'btn' is a button"])
    assert plan["dropped_tests"] == [
        {"test": "negative — empty", "reason": "placeholder_negative_dropped"},
        {"test": "negative — x", "reason": "locator_type_mismatch",
         "detail": "negative — x: enterText('btn') — 'btn' is a button"}]
    assert record_drops({"tests": []}, [], []) == {"tests": []}
