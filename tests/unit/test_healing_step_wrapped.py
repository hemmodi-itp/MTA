"""Phase 4.5 / 4.6 / 4.7 — healing on step-wrapped specs: block extraction, the details-object guard, the new
fixed-sleep guard, the timing fix's web-first suggestion, and "flaky after a patch" is not healed."""

import logging

import pytest

import agents.test_execution.healing.tools as ht
from agents.test_execution.healing.tools import HealingRunContext, _apply_patch, _extract_test_block, _run_tests
from tools.test_creation.script_generator.compose import compose_spec

TITLE = "AC-03.3.1 price empty is rejected"
PLAN = {"tests": [{"name": "price empty is rejected", "type": "negative", "priority": "P0", "tc_id": "M03_TC_005",
                   "ac_ids": ["AC-03.3.1"], "steps": [
                       {"action": "navigate", "value": "/products/new"},
                       {"action": "click", "locator_key": "save_button"},
                       {"action": "verifyContainsText", "locator_key": "errors", "value": "Price is required"}]}]}
REL = "M03/test_M03_BS_001_x.spec.ts"


@pytest.fixture
def ctx(tmp_path):
    scripts = tmp_path / "test_scripts" / "M03"
    scripts.mkdir(parents=True)
    spec = compose_spec(PLAN, {"scenario_id": "M03_BS_001", "title": "Create"}, "http://127.0.0.1:1/products/new",
                        f"projects/p/test_creation/test_scripts/{REL}", test_steps=True)
    (scripts / "test_M03_BS_001_x.spec.ts").write_text(spec, encoding="utf-8")
    return HealingRunContext(
        project_name="p", scripts_dir=str(tmp_path / "test_scripts"), reports_dir=str(tmp_path),
        report_json="", dom_elements=[], module_urls={}, default_url="https://x.test", test_data_map={},
        settings={}, logger=logging.getLogger("t"))


def _block(ctx):
    return _extract_test_block(open(f"{ctx.scripts_dir}/{REL}", encoding="utf-8").read(), TITLE)


def test_extracts_the_whole_step_wrapped_block(ctx):
    block = _block(ctx)
    assert block.count("await test.step(") == 3 and block.rstrip().endswith("});")
    assert 'await action.verifyContainsText("errors", "Price is required");' in block


def test_patch_inside_a_step_applies_and_keeps_the_details_object(ctx):
    new = _block(ctx).replace('action.click("save_button")', 'action.click("save_product_button")')
    assert _apply_patch(ctx, REL, TITLE, new)["applied"] is True
    assert 'action.click("save_product_button")' in open(f"{ctx.scripts_dir}/{REL}", encoding="utf-8").read()


def test_details_guard_still_rejects_a_dropped_details_object(ctx):
    block = _block(ctx)
    header = block.splitlines()[0]
    new = block.replace(header, f'  test("{TITLE}", async ({{ action }}) => {{')
    out = _apply_patch(ctx, REL, TITLE, new)
    assert out["applied"] is False and "tag: [...], annotation: [...]" in out["reason"]


@pytest.mark.parametrize("sleep", ['await action.waitForTimeout(2000);', 'await page.waitForTimeout(500);',
                                   'await new Promise((r) => setTimeout(r, 1000));'])
def test_apply_patch_rejects_an_added_fixed_sleep(ctx, sleep):
    new = _block(ctx).replace('      await action.click("save_button");', f'      {sleep}\n      await action.click("save_button");')
    out = _apply_patch(ctx, REL, TITLE, new)
    assert out["applied"] is False and "fixed sleep" in out["reason"] and "web-first" in out["reason"]


def test_a_sleep_the_block_already_had_may_stay(ctx):
    path = f"{ctx.scripts_dir}/{REL}"
    text = open(path, encoding="utf-8").read().replace('      await action.click("save_button");',
                                                        '      await action.waitForTimeout(200);\n      await action.click("save_button");')
    open(path, "w", encoding="utf-8").write(text)
    new = _block(ctx).replace('action.click("save_button")', 'action.click("save_product_button")')
    assert _apply_patch(ctx, REL, TITLE, new)["applied"] is True


def test_timing_fix_suggests_a_web_first_wait_never_a_sleep(ctx, monkeypatch):
    raw = (f"  test(\"{TITLE}\", async ({{ page }}) => {{\n"
           "    await page.getByRole('button', { name: 'Save' }).click();\n  });\n")
    monkeypatch.setattr(ht, "_read_test_block", lambda c, s, t: raw)

    class _Page:
        pass

    monkeypatch.setattr(ht, "_get_validation_page", lambda c, m="": (None, _Page()))

    class _Loc:
        def wait_for(self, timeout):
            return None

    monkeypatch.setattr(ht, "_build_python_locator", lambda *a, **k: _Loc())

    class _Exec:
        def submit(self, fn):
            fn()
            return type("F", (), {"result": lambda self: None})()

    monkeypatch.setattr(HealingRunContext, "pw_executor", lambda self: _Exec())
    out = ht._propose_timing_fix(ctx, REL, TITLE)
    assert out["is_timing_issue"] is True
    assert out["suggested_fix"] == ("await expect(page.getByRole('button', { name: 'Save' }), "
                                    "'element should be visible before it is used').toBeVisible();")
    assert "waitForTimeout" not in out["suggested_fix"] and "rejects fixed sleeps" in out["forbidden"]


def test_flaky_after_a_patch_is_not_counted_as_healed(ctx, monkeypatch):
    ctx.remaining = {REL: {TITLE: "old error"}}

    class _Agent:
        def __init__(self, settings=None):
            pass

        def execute(self, request, state):
            return {"status": "success", "passed": 0, "failed": 0, "flaky": 1, "results": [
                {"spec_file": f"p/test_creation/test_scripts/{REL}", "test_title": TITLE, "status": "flaky",
                 "errors": ["Timeout on attempt 1"]}]}

    import agents.test_execution.ui_execution.agent as ui
    monkeypatch.setattr(ui, "UIExecutionAgent", _Agent)
    out = _run_tests(ctx, [REL])
    assert out["all_resolved"] is False
    assert ctx.remaining[REL][TITLE].startswith("flaky after the patch — passed only on a retry")
