// Phase 4.8 acceptance — a second and third spec file so a 2-shard run has work for both shards
// (without fullyParallel, Playwright shards by file). Anonymous pages only: no role needed.
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe('P4 pages A', () => {
  test('login page renders', { tag: ['@P4', '@smoke'], annotation: [{ type: 'tc', description: 'P4_TC_010' }] }, async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('#login-button')).toBeVisible();
  });

  test('help page renders', { tag: ['@P4'], annotation: [{ type: 'tc', description: 'P4_TC_011' }] }, async ({ page }) => {
    const response = await page.goto('/help');
    expect(response?.status()).toBe(200);
  });

  test('health endpoint answers', { tag: ['@P4', '@api'], annotation: [{ type: 'tc', description: 'P4_TC_012' }] }, async ({ request }) => {
    const response = await request.get('/api/health');
    expect(response.ok()).toBe(true);
  });
});
