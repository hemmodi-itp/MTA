// Phase 4 acceptance criterion 7 — consoleGuard fails a test on a NEW console error but not on a baseline one.
// The project sets execution.console_guard: fail; its baseline.json records the 403 console error the user role
// gets on /admin (as Phase 2 discovery recorded it). Copied into bench_p4b_e2e/test_creation/test_scripts/P4B/.
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ role: 'user' });

test.describe('console guard (P4_BS_003)', () => {
  test('baseline console error does not fail', { tag: ['@console'] }, async ({ page, consoleGuard }) => {
    await page.goto('/admin');
    await expect(page.getByText('Access denied').first()).toBeVisible();
    expect(consoleGuard.knownErrors().length, 'the 403 resource error was seen and is in the baseline').toBeGreaterThan(0);
  });

  test('new console error fails the test', { tag: ['@console'] }, async ({ page }) => {
    await page.goto('/products/999999');
    await expect(page.getByText('not found').first()).toBeVisible();
    // the body passes — consoleGuard fails it at teardown: the 404 resource error is not in the baseline
  });
});
