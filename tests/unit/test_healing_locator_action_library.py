import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.healing.tools import (
    HealingRunContext,
    _locator_entry_resolves,
    _propose_locator_fix,
)


def _ctx(tmp, generation_modes, locator_map, scripts_dir):
    return HealingRunContext(
        project_name="proj",
        scripts_dir=scripts_dir,
        reports_dir=os.path.join(tmp, "reports"),
        report_json=os.path.join(tmp, "reports", "json", "x_results.json"),
        dom_elements=[],
        module_urls={},
        default_url="https://example.com",
        test_data_map={},
        settings={},
        logger=MagicMock(),
        generation_modes=generation_modes,
        locator_map=locator_map,
        locator_map_path=os.path.join(tmp, "locator_map.json"),
        comprehension_dir=os.path.join(tmp, "test_comprehension"),
    )


def _write_spec(scripts_dir, spec_file, content):
    path = os.path.join(scripts_dir, spec_file)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


_ACTION_LIBRARY_SPEC = """import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Login (M01_BS_001)", () => {

  test("positive — login @smoke", async ({ action }) => {
    await action.enterText("username_input", "bob");
    await action.click("login_button");
  });

});
"""


class LocatorEntryResolvesTests(unittest.TestCase):
    def test_css_resolves(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 1
        self.assertTrue(_locator_entry_resolves(page, {"type": "css", "locator": "#x"}))

    def test_zero_count_is_unresolved(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 0
        self.assertFalse(_locator_entry_resolves(page, {"type": "css", "locator": "#x"}))


class ProposeLocatorFixActionLibraryTests(unittest.TestCase):
    """propose_locator_fix must branch to the locator_map.json repair path
    for an action-library spec, and leave the legacy raw-locator path
    completely untouched for anything else."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.scripts_dir = os.path.join(self.tmp, "test_scripts")
        _write_spec(self.scripts_dir, "M01/test_x.spec.ts", _ACTION_LIBRARY_SPEC)

    def test_branches_to_action_library_path_when_generation_mode_matches(self):
        locator_map = {
            "username_input": {"type": "css", "locator": "#username", "_module_id": "M01", "_source_locator_id": "LOC-0001"},
        }
        ctx = _ctx(self.tmp, {"M01/test_x.spec.ts": "action_library"}, locator_map, self.scripts_dir)

        page = MagicMock()
        page.locator.return_value.count.return_value = 0  # broken

        with patch("agents.test_execution.healing.tools._get_validation_page", return_value=(None, page)):
            with patch("agents.test_execution.healing.tools.repair_named_locator", return_value=True) as repair:
                with patch("builtins.open", side_effect=_open_locator_map_stub(locator_map)):
                    result = _propose_locator_fix(ctx, "M01/test_x.spec.ts", "positive — login @smoke")

        repair.assert_called_once_with(ctx.locator_map_path, ctx.comprehension_dir, "username_input")
        self.assertTrue(result["resolved"])
        self.assertTrue(result["applied"])
        self.assertEqual(result["repaired_key"], "username_input")

    def test_key_that_already_resolves_is_not_touched(self):
        locator_map = {
            "username_input": {"type": "css", "locator": "#username", "_module_id": "M01"},
            "login_button": {"type": "css", "locator": "#login", "_module_id": "M01"},
        }
        ctx = _ctx(self.tmp, {"M01/test_x.spec.ts": "action_library"}, locator_map, self.scripts_dir)

        page = MagicMock()
        page.locator.return_value.count.return_value = 1  # both resolve fine

        with patch("agents.test_execution.healing.tools._get_validation_page", return_value=(None, page)):
            with patch("agents.test_execution.healing.tools.repair_named_locator") as repair:
                result = _propose_locator_fix(ctx, "M01/test_x.spec.ts", "positive — login @smoke")

        repair.assert_not_called()
        self.assertFalse(result["resolved"])

    def test_legacy_spec_uses_unchanged_raw_locator_path(self):
        legacy_spec = (
            "import { test, expect } from '@playwright/test';\n"
            "test.describe('Legacy', () => {\n"
            "  test('positive — x', async ({ page }) => {\n"
            "    await page.getByPlaceholder('Ghost').fill('x');\n"
            "  });\n"
            "});\n"
        )
        _write_spec(self.scripts_dir, "M01/test_legacy.spec.ts", legacy_spec)
        ctx = _ctx(self.tmp, {}, {}, self.scripts_dir)  # no generation_mode entry at all

        with patch("agents.test_execution.healing.tools._get_validation_page", return_value=(None, None)):
            result = _propose_locator_fix(ctx, "M01/test_legacy.spec.ts", "positive — x")

        # Falls into the legacy path (validation page unavailable is the
        # legacy path's own message) rather than the action-library path.
        self.assertIn("headless validation page unavailable", result["reason"])

    def test_no_action_call_in_block_is_reported(self):
        _write_spec(self.scripts_dir, "M01/test_empty.spec.ts", (
            "test.describe('X', () => { test('positive — x', async ({ action }) => {}); });"
        ))
        ctx = _ctx(self.tmp, {"M01/test_empty.spec.ts": "action_library"}, {}, self.scripts_dir)
        result = _propose_locator_fix(ctx, "M01/test_empty.spec.ts", "positive — x")
        self.assertFalse(result["resolved"])
        self.assertIn("no action.<verb>", result["reason"])


def _open_locator_map_stub(locator_map):
    """Patch builtins.open so repair_named_locator's post-repair re-read of
    locator_map.json inside _propose_locator_fix_action_library succeeds
    without touching the real filesystem for that one read."""
    import io
    real_open = open

    def _fake_open(path, *args, **kwargs):
        if str(path).endswith("locator_map.json"):
            return io.StringIO(json.dumps(locator_map))
        return real_open(path, *args, **kwargs)
    return _fake_open


if __name__ == "__main__":
    unittest.main()
