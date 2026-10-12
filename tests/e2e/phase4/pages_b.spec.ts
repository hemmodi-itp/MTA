// Phase 4.8 acceptance — third spec file for the shard/merge totals check.
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe('P4 pages B', () => {
  test('unknown page is a 404', { tag: ['@P4'], annotation: [{ type: 'tc', description: 'P4_TC_020' }] }, async ({ page }) => {
    const response = await page.goto('/no-such-page');
    expect(response?.status()).toBe(404);
  });

  test('root redirects to products (then login for a guest)', { tag: ['@P4'], annotation: [{ type: 'tc', description: 'P4_TC_021' }] }, async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/login/);
  });

  test('a deliberately failing check shows up as failed with evidence', {
    tag: ['@P4', '@evidence'],
    annotation: [{ type: 'tc', description: 'P4_TC_022' }, { type: 'ac', description: 'AC-99.1' }],
  }, async ({ page }) => {
    await page.goto('/login');
    // Fails on purpose: proves a failure keeps its screenshot / trace / video (retain-on-failure,
    // and --output no longer shares the HTML report folder) and is linked in JUnit + MTA output.
    await expect(page.locator('#login-button')).toHaveText('this text is not on the page', { timeout: 1500 });
  });
});
