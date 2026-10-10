"""Phase 1.3 — healing may patch a test's body but never drop or alter its { tag, annotation } details object
(the test's link to its acceptance criteria). Specs without a details object are unaffected."""

import logging
import os

import pytest

from agents.test_execution.healing.tools import HealingRunContext, _apply_patch, _header_details

DETAILS = ('{ tag: ["@P1", "@negative", "@regression", "@REQ-01", "@AC-01.2"], annotation: '
           '[{ type: "ac", description: "AC-01.2" }, { type: "tc", description: "M01_TC_002" }] }')
TITLE = "AC-01.2 negative — wrong password"
SPEC = f"""import {{ test, expect }} from '../fixture';

test.describe("Failed login (M01_BS_002)", () => {{

  test("{TITLE}", {DETAILS}, async ({{ action }}) => {{
    await action.click("old_button");
  }});

  test("legacy — no details @smoke", async ({{ action }}) => {{
    await action.click("old_button");
  }});

}});
"""


@pytest.fixture
def ctx(tmp_path):
    scripts = tmp_path / "test_scripts" / "M01"
    scripts.mkdir(parents=True)
    (scripts / "test_M01_BS_002.spec.ts").write_text(SPEC, encoding="utf-8")
    return HealingRunContext(
        project_name="p", scripts_dir=str(tmp_path / "test_scripts"), reports_dir=str(tmp_path),
        report_json="", dom_elements=[], module_urls={}, default_url="https://x.test", test_data_map={},
        settings={}, logger=logging.getLogger("t"))


def _spec(ctx):
    return open(os.path.join(ctx.scripts_dir, "M01", "test_M01_BS_002.spec.ts"), encoding="utf-8").read()


def test_header_details_extraction():
    assert _header_details(f'  test("{TITLE}", {DETAILS}, async ({{ action }}) => {{\n  }});') == DETAILS
    assert _header_details('  test("plain", async ({ action }) => {\n  });') is None


def test_patch_keeping_details_is_applied(ctx):
    new = f'  test("{TITLE}", {DETAILS}, async ({{ action }}) => {{\n    await action.click("new_button");\n  }});'
    res = _apply_patch(ctx, "M01/test_M01_BS_002.spec.ts", TITLE, new)
    assert res["applied"] is True and 'click("new_button")' in _spec(ctx)


def test_skip_conversion_keeping_details_is_applied(ctx):
    new = (f'  test.skip("no locator for: login button", {DETAILS}, async ({{ action }}) => {{\n'
           f'    await action.click("old_button");\n  }});')
    assert _apply_patch(ctx, "M01/test_M01_BS_002.spec.ts", TITLE, new)["applied"] is True


@pytest.mark.parametrize("new_header", [
    f'  test("{TITLE}", async ({{ action }}) => {{',                                         # details dropped
    f'  test("{TITLE}", {DETAILS.replace("AC-01.2", "AC-01.1")}, async ({{ action }}) => {{',  # ac changed
    f'  test.skip("no locator for: x", async ({{ action }}) => {{',                           # skip w/o details
])
def test_patch_dropping_or_changing_details_is_rejected(ctx, new_header):
    before = _spec(ctx)
    res = _apply_patch(ctx, "M01/test_M01_BS_002.spec.ts", TITLE, new_header + '\n    await action.click("x");\n  });')
    assert res["applied"] is False and "tag: [...], annotation: [...]" in res["reason"]
    assert DETAILS in res["reason"]                     # the error tells the model exactly what to keep
    assert _spec(ctx) == before and ctx.tests_healed == 0


def test_multiline_details_are_rejected(ctx):
    new = (f'  test("{TITLE}", {{\n    tag: ["@P1"],\n    annotation: [] }}, async ({{ action }}) => {{\n'
           f'    await action.click("x");\n  }});')
    assert _apply_patch(ctx, "M01/test_M01_BS_002.spec.ts", TITLE, new)["applied"] is False


def test_specs_without_details_are_unaffected(ctx):
    new = '  test("legacy — no details @smoke", async ({ action }) => {\n    await action.click("fixed");\n  });'
    assert _apply_patch(ctx, "M01/test_M01_BS_002.spec.ts", "legacy — no details @smoke", new)["applied"] is True


def test_prompt_tells_the_model_to_keep_details():
    from agents.test_execution.healing.prompt import SUPERVISOR_INSTRUCTION

    assert "{ tag: [...], annotation: [...] }" in SUPERVISOR_INSTRUCTION
