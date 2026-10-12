// Phase 4 acceptance criterion 2 — two parallel workers run the same create flow without data collisions.
// Copied by tests/integration/test_phase4b_runtime_e2e.py into bench_p4b_e2e/test_creation/test_scripts/P4B/
// (the import below is relative to that folder). The project sets execution.data_isolation: true, so
// fullyParallel spreads these tests of ONE file over both workers.
//
// buggy_shop silently de-duplicates a product created with the same name + price within 5 s (it returns the
// existing product), so two workers using the same literal data would land on each other's product.
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ role: 'user' });

const PRICE = '9.99';

async function createProduct(page: any, name: string): Promise<number> {
  await page.goto('/products/new');
  await page.locator('#name').fill(name);
  await page.locator('#price').fill(PRICE);
  await page.locator('#category').selectOption('Books');
  await page.locator('#save-product').click();
  await expect(page).toHaveURL(/\/products\/\d+$/);
  return Number(new URL(page.url()).pathname.split('/').pop());
}

test.describe('create flow under parallel workers (P4_BS_002)', () => {
  for (let i = 1; i <= 6; i++) {
    test(`isolated create ${i}`, { tag: ['@isolation'] }, async ({ page, testData, cleanup }, testInfo) => {
      const started = Date.now();
      const name = testData.unique('Widget', { maxLength: 50 });
      const id = await createProduct(page, name);
      cleanup.register(`product ${id}`, {
        api: async (api) => {
          const res = await api.post(`/products/${id}/delete`, { maxRedirects: 0 });
          expect([200, 303], `delete product ${id}`).toContain(res.status());
        },
      });
      // the product page shows OUR product, not another worker's
      await expect(page.locator('#product-name')).toHaveText(name);
      // keep the test running long enough that the two workers overlap
      await expect(page.locator('#product-name')).toBeVisible();
      testInfo.annotations.push({
        type: 'created',
        description: JSON.stringify({ worker: testInfo.parallelIndex, id, name, prefix: testData.prefix, started, ended: Date.now() }),
      });
    });
  }

  test('control: the same literal data collides', { tag: ['@control'] }, async ({ page, cleanup }) => {
    const name = `p4b-literal-${Date.now()}`;
    const first = await createProduct(page, name);
    const second = await createProduct(page, name);
    cleanup.register(`product ${first}`, { api: async (api) => { await api.post(`/products/${first}/delete`, { maxRedirects: 0 }); } });
    // within the 5 s de-dup window the second create returns the first product: a collision
    expect(second, 'same name + price within 5 s returns the existing product').toBe(first);
  });
});
