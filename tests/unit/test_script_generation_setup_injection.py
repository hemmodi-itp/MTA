import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.script_generation.agent import (
    _inject_setup_steps,
    _translate_setup_step,
)

_SAMPLE_SPEC = """import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Sort Products (BS-006)', () => {

  test('positive — sorts correctly', async ({ page }) => {
    await page.goto(BASE_URL);
  });

});
"""

_M02_SETUP = [
    {"goto": "https://www.saucedemo.com/"},
    {"fill": {"selector": "[data-test='username']", "value": "standard_user"}},
    {"fill": {"selector": "[data-test='password']", "value": "secret_sauce"}},
    {"click": "[data-test='login-button']"},
    {"wait": 2000},
]


class TranslateSetupStepTests(unittest.TestCase):
    def test_goto(self):
        self.assertEqual(
            _translate_setup_step({"goto": "https://example.com/"}),
            "    await page.goto(\"https://example.com/\");",
        )

    def test_fill(self):
        step = {"fill": {"selector": "#user", "value": "bob"}}
        self.assertEqual(
            _translate_setup_step(step),
            '    await page.locator("#user").fill("bob");',
        )

    def test_click(self):
        self.assertEqual(
            _translate_setup_step({"click": "#submit"}),
            '    await page.locator("#submit").click();',
        )

    def test_wait(self):
        self.assertEqual(_translate_setup_step({"wait": 1500}), "    await page.waitForTimeout(1500);")

    def test_unknown_action_returns_empty(self):
        self.assertEqual(_translate_setup_step({"hover": "#thing"}), "")

    def test_fill_missing_selector_returns_empty(self):
        self.assertEqual(_translate_setup_step({"fill": {"value": "bob"}}), "")

    def test_wait_non_numeric_returns_empty(self):
        self.assertEqual(_translate_setup_step({"wait": "soon"}), "")

    def test_escapes_special_characters_safely(self):
        # Values containing quotes must be escaped, not break out of the string literal.
        step = {"fill": {"selector": "#user", "value": 'a"b\\c'}}
        translated = _translate_setup_step(step)
        self.assertEqual(translated, '    await page.locator("#user").fill("a\\"b\\\\c");')

    def test_fill_value_env_emits_process_env_reference_not_literal(self):
        # The actual secret must never be embedded in generated source — only
        # a reference to be resolved by Playwright at test run time.
        step = {"fill": {"selector": "#username", "value_env": "APPEVOLVE_AUTOMATION_DEV_USERNAME"}}
        translated = _translate_setup_step(step)
        self.assertEqual(
            translated,
            '    await page.locator("#username").fill(process.env.APPEVOLVE_AUTOMATION_DEV_USERNAME ?? "");',
        )

    def test_fill_value_env_takes_precedence_over_value(self):
        step = {"fill": {"selector": "#username", "value_env": "SOME_VAR", "value": "should_not_appear"}}
        translated = _translate_setup_step(step)
        self.assertIn("process.env.SOME_VAR", translated)
        self.assertNotIn("should_not_appear", translated)

    def test_fill_value_env_rejects_unsafe_identifier(self):
        # A malformed env var name must never be interpolated as raw code.
        step = {"fill": {"selector": "#username", "value_env": "NOT; VALID_JS"}}
        self.assertEqual(_translate_setup_step(step), "")


class InjectSetupBeforeEachTests(unittest.TestCase):
    def test_injects_before_each_after_describe_open(self):
        result = _inject_setup_steps(_SAMPLE_SPEC, _M02_SETUP)

        self.assertIn("test.beforeEach(async ({ page }) => {", result)
        self.assertIn('await page.goto("https://www.saucedemo.com/");', result)
        self.assertIn('await page.locator("[data-test=\'username\']").fill("standard_user");', result)
        self.assertIn("await page.waitForTimeout(2000);", result)
        # beforeEach must appear before the first test(...) block
        self.assertLess(result.index("beforeEach"), result.index("test('positive"))

    def test_returns_unchanged_when_no_setup_steps(self):
        self.assertEqual(_inject_setup_steps(_SAMPLE_SPEC, None), _SAMPLE_SPEC)
        self.assertEqual(_inject_setup_steps(_SAMPLE_SPEC, []), _SAMPLE_SPEC)

    def test_returns_unchanged_when_describe_anchor_not_found(self):
        broken_spec = "// no describe block here\n"
        self.assertEqual(_inject_setup_steps(broken_spec, _M02_SETUP), broken_spec)

    def test_skips_unknown_steps_but_keeps_known_ones(self):
        steps = [{"goto": "https://example.com/"}, {"hover": "#thing"}]
        result = _inject_setup_steps(_SAMPLE_SPEC, steps)

        self.assertIn('await page.goto("https://example.com/");', result)
        self.assertNotIn("hover", result)

    def test_returns_unchanged_when_all_steps_unknown(self):
        result = _inject_setup_steps(_SAMPLE_SPEC, [{"hover": "#thing"}])
        self.assertEqual(result, _SAMPLE_SPEC)


_SHARED_PAGE_SPEC = """import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe.configure({ mode: 'serial' });

test.describe('Sort Products (BS-006)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — sorts correctly', async () => {
    await page.goto(BASE_URL);
  });

});
"""


class InjectSetupStepsSharedPageTests(unittest.TestCase):
    def test_injects_into_beforeAll_right_after_newPage(self):
        result = _inject_setup_steps(_SHARED_PAGE_SPEC, _M02_SETUP)

        self.assertIn('page = await browser.newPage();', result)
        self.assertIn('await page.goto("https://www.saucedemo.com/");', result)
        self.assertIn('await page.locator("[data-test=\'username\']").fill("standard_user");', result)
        # setup lines land inside beforeAll, before afterAll/test blocks
        self.assertLess(result.index('newPage()'), result.index("standard_user"))
        self.assertLess(result.index("standard_user"), result.index("afterAll"))
        # must NOT also inject a legacy beforeEach when the beforeAll anchor matched
        self.assertNotIn("beforeEach", result)

    def test_does_not_duplicate_hook_when_no_setup_steps(self):
        self.assertEqual(_inject_setup_steps(_SHARED_PAGE_SPEC, None), _SHARED_PAGE_SPEC)


if __name__ == "__main__":
    unittest.main()
