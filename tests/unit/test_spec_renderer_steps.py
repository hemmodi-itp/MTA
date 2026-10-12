"""Phase 4.5 — one test.step per plan step, test.use({ role }) for modules, web-first module setup (golden snapshots)."""

import re

import pytest

from agents.test_execution.healing.tools import _extract_test_block, _header_details, _structurally_valid_block
from tools.test_creation.script_generator.compose import compose_spec, inject_role, module_role_for
from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan, step_title

SPEC_REL = "projects/shop/test_creation/test_scripts/M03/test_M03_BS_001_create.spec.ts"
SCENARIO = {"scenario_id": "M03_BS_001", "title": "Create product"}
URL = "http://127.0.0.1:8765/products/new"
SETUP = [{"goto": "http://127.0.0.1:8765/login"}, {"fill": {"selector": "#username", "value": "alice"}},
         {"fill": {"selector": "#password", "value": "alice-pass-1"}}, {"click": "#login-button"}, {"wait": 500}]

TRACED = {"tests": [{
    "name": "price empty is rejected", "type": "negative", "priority": "P0", "tc_id": "M03_TC_005",
    "ac_ids": ["AC-03.3.1"], "req_ids": ["REQ-03"], "technique": "ep", "case_id": "TC-a21f1f4b",
    "steps": [
        {"action": "navigate", "value": "/products/new"},
        {"action": "enterText", "locator_key": "price", "value": ""},
        {"action": "click", "locator_key": "save_product_button"},
        {"action": "verifyContainsText", "locator_key": "product_form_errors", "value": "Price is required",
         "message": "Error message should state that price is required"},
    ],
}]}

GOLDEN_STEPS = '''// Base URL (from project.yaml, resolved via playwright.config.ts): http://127.0.0.1:8765/products/new
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ baseURL: "http://127.0.0.1:8765/products/new" });

test.describe("Create product (M03_BS_001)", () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("http://127.0.0.1:8765/login");
    await page.locator("#username").fill("alice");
    await page.locator("#password").fill("alice-pass-1");
    await page.locator("#login-button").click();
    await page.waitForLoadState('load');
  });
  test("AC-03.3.1 price empty is rejected", { tag: ["@P0", "@negative", "@regression", "@REQ-03", "@AC-03.3.1", "@ep"], annotation: [{ type: "ac", description: "AC-03.3.1" }, { type: "tc", description: "M03_TC_005" }, { type: "case", description: "TC-a21f1f4b" }, { type: "scenario", description: "M03_BS_001" }] }, async ({ action }) => {
    await test.step("1. Navigate to \\"/products/new\\"", async () => {
      await action.navigate("/products/new");
    });
    await test.step("2. Enter \\"\\" into \\"price\\"", async () => {
      await action.enterText("price", "");
    });
    await test.step("3. Click \\"save_product_button\\"", async () => {
      await action.click("save_product_button");
    });
    await test.step("4. Verify \\"product_form_errors\\" contains \\"Price is required\\" \u2014 Error message should state that price is required", async () => {
      await action.verifyContainsText("product_form_errors", "Price is required", "Error message should state that price is required");
    });
  });

});
'''

GOLDEN_ROLE_HEAD = '''// Base URL (from project.yaml, resolved via playwright.config.ts): http://127.0.0.1:8765/products/new
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ baseURL: "http://127.0.0.1:8765/products/new" });
test.use({ role: "user" });

test.describe("Create product (M03_BS_001)", () => {

  test("AC-03.3.1 price empty is rejected", { tag: ['''


def _compose(plan=TRACED, **kw):
    kw.setdefault("module_setup", SETUP)
    return compose_spec(plan, SCENARIO, URL, SPEC_REL, project="shop", **kw)


def test_golden_test_steps_with_module_setup():
    assert _compose(test_steps=True) == GOLDEN_STEPS


def test_golden_role_replaces_the_setup_before_each():
    spec = _compose(test_steps=True, role="user")
    assert spec.startswith(GOLDEN_ROLE_HEAD)
    assert "beforeEach" not in spec and "alice-pass-1" not in spec and "waitForTimeout" not in spec


def test_legacy_rendering_is_unchanged_without_test_steps():
    flat = render_spec_from_plan(TRACED, SCENARIO, URL, SPEC_REL, project="shop")
    assert "test.step" not in flat
    assert '    await action.click("save_product_button");' in flat


def test_one_step_per_plan_step_and_tags_annotations_stay_on_the_test_line():
    spec = _compose(test_steps=True)
    assert spec.count("await test.step(") == len(TRACED["tests"][0]["steps"])
    test_line = next(ln for ln in spec.splitlines() if ln.startswith('  test("'))
    assert '{ tag: ["@P0", "@negative"' in test_line and '{ type: "tc", description: "M03_TC_005" }' in test_line
    assert test_line.endswith("async ({ action }) => {")


def test_untraced_test_keeps_title_tag_and_gets_steps():
    plan = {"tests": [{"name": "valid login", "type": "positive", "steps": [{"action": "click", "locator_key": "go"}]}]}
    spec = render_spec_from_plan(plan, SCENARIO, URL, SPEC_REL, test_steps=True)
    assert '  test("valid login @smoke", async ({ action }) => {' in spec
    assert '    await test.step("1. Click \\"go\\"", async () => {' in spec


@pytest.mark.parametrize("step, expected", [
    ({"action": "navigate"}, "1. Open the module page"),
    ({"action": "pressKey", "value": "Enter"}, '1. Press "Enter"'),
    ({"action": "pressKey", "locator_key": "search", "value": "Enter"}, '1. Press "Enter" in "search"'),
    ({"action": "selectDropdownByText", "locator_key": "category", "value": "Books"}, '1. Select "Books" in "category"'),
    ({"action": "waitForElement", "locator_key": "toast"}, '1. Wait for "toast" to be visible'),
    ({"action": "dragAndDrop", "locator_key": "a", "target_locator_key": "b"}, '1. Drag "a" onto "b"'),
    ({"action": "verifyCount", "locator_key": "rows", "value": 3}, '1. Verify "rows" count is 3'),
    ({"action": "verifyHidden", "locator_key": "err"}, '1. Verify "err" is hidden'),
    ({"action": "waitForTimeout", "value": 500}, "1. Wait 500 ms (fixed sleep)"),
    ({"action": "verifyNoPageErrors"}, "1. Verify no page errors"),
])
def test_step_titles(step, expected):
    assert step_title(1, step) == expected


def test_secret_values_are_masked_in_step_titles():
    assert step_title(2, {"action": "enterText", "locator_key": "password", "value": "alice-pass-1"}) == \
        '2. Enter \u2022\u2022\u2022 into "password"'
    # masked through the locator entry too (an input whose key doesn't say it)
    lm = {"input_loc_7": {"type": "label", "locator": "Password"}}
    assert "pw-1" not in step_title(1, {"action": "enterText", "locator_key": "input_loc_7", "value": "pw-1"}, lm)
    t = step_title(1, {"action": "useFlow", "flow": "login", "args": {"username": "alice", "password": "s3cret"}})
    assert t == '1. Flow login(username="alice", password=\u2022\u2022\u2022)'


def test_step_titles_never_leave_unbalanced_brackets():
    t = step_title(1, {"action": "enterText", "locator_key": "name", "value": "Widget (blue"})
    assert t == '1. Enter <value> into "name"'
    t = step_title(1, {"action": "click", "locator_key": "go", "message": "opens the (menu"})
    assert t == '1. Click "go"'
    long = step_title(1, {"action": "verifyText", "locator_key": "x", "value": "a" * 300, "message": "m " * 200})
    assert len(long) <= 160 and long.count("(") == long.count(")")


def test_healing_extracts_and_validates_step_wrapped_blocks():
    spec = _compose(test_steps=True)
    block = _extract_test_block(spec, "AC-03.3.1 price empty is rejected")
    assert block.startswith('  test("AC-03.3.1 price empty is rejected", { tag:')
    assert block.rstrip().endswith("});") and block.count("await test.step(") == 4
    assert _structurally_valid_block(block)
    assert _header_details(block).startswith("{ tag: [")


def test_module_role_resolution():
    warnings = []
    assert module_role_for("user", True, ["user", "admin"], True, warnings.append) == "user"
    assert module_role_for("user", False, ["user"], True, warnings.append) is None           # flag off
    assert module_role_for(None, True, ["user"], True, warnings.append) is None               # module has no role
    assert module_role_for("ghost", True, ["user"], True, warnings.append) is None            # undeclared -> setup
    assert module_role_for("user", True, ["user"], False, warnings.append) == "user"          # role_auth off: warn
    assert any("ghost" in w for w in warnings) and any("role_auth is off" in w for w in warnings)


def test_inject_role_without_base_url_goes_after_imports():
    spec = "import { test } from './x';\n\ntest.describe(\"t\", () => {\n});\n"
    assert inject_role(spec, "admin").startswith('import { test } from \'./x\';\n\ntest.use({ role: "admin" });\n')


def test_raw_fallback_specs_keep_the_setup_injection_even_with_a_role():
    raw = "test.describe(\"legacy\", () => {\n  test('x', async () => {});\n});\n"
    out = compose_spec(None, SCENARIO, URL, SPEC_REL, module_setup=SETUP, role="user", raw_content=raw)
    assert "test.beforeEach" in out and "test.use({ role" not in out


def test_no_wait_for_timeout_anywhere_in_a_rendered_generated_spec():
    assert not re.search(r"waitForTimeout", _compose(test_steps=True))
