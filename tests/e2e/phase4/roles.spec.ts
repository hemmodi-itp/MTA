// Phase 4.3 acceptance — per-role auth on buggy_shop: two logged-in roles + anonymous.
// Copied by tests/integration/test_phase4_runtime_e2e.py into
// application_assets/projects/bench_p4_e2e/test_creation/test_scripts/P4/ and run through
// UIExecutionAgent (execution.role_auth: true writes .auth/user.json and .auth/admin.json first).
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe('P4 roles — admin', () => {
  test.use({ role: 'admin' });

  test('admin reaches the admin page', {
    tag: ['@P4', '@roles', '@P0'],
    annotation: [{ type: 'tc', description: 'P4_TC_001' }, { type: 'ac', description: 'AC-06.1' }],
  }, async ({ page }) => {
    const response = await page.goto('/admin');
    expect(response?.status()).toBe(200);
    // getByTestId reads execution.test_id_attribute — data-testid, which buggy_shop uses.
    await expect(page.getByTestId('nav-admin')).toBeVisible();
  });
});

test.describe('P4 roles — user', () => {
  test.use({ role: 'user' });

  test('user is denied the admin page', {
    tag: ['@P4', '@roles', '@P1'],
    annotation: [{ type: 'tc', description: 'P4_TC_002' }, { type: 'ac', description: 'AC-06.2' }],
  }, async ({ page }) => {
    const response = await page.goto('/admin');
    expect(response?.status()).toBe(403);
    await expect(page.getByText('Access denied').first()).toBeVisible();
  });

  test('user sees the product list without logging in again', {
    tag: ['@P4', '@roles', '@smoke'],
    annotation: [{ type: 'tc', description: 'P4_TC_003' }, { type: 'ac', description: 'AC-02.1' }],
  }, async ({ page }) => {
    await page.goto('/products');
    await expect(page).toHaveURL(/\/products/);
    await expect(page.getByTestId('nav-admin')).toHaveCount(0);
  });
});

test.describe('P4 roles — guest (anonymous)', () => {
  test.use({ role: 'guest' });

  test('guest is sent to the login page', {
    tag: ['@P4', '@roles', '@P1'],
    annotation: [{ type: 'tc', description: 'P4_TC_004' }, { type: 'ac', description: 'AC-01.4' }],
  }, async ({ page }) => {
    await page.goto('/products');
    await expect(page).toHaveURL(/\/login\?next=/);
  });
});
