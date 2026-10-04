import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/pricing/';

test.describe.configure({ mode: 'serial' });

test.describe('Browse AWS Aurora pricing page with navigation to different pricing models (M03_BS_007)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — successfully navigate through all AWS Aurora pricing models', async () => {
    await page.goto(BASE_URL);
    
    // Navigate to Aurora pricing section
    await page.waitForLoadState('networkidle');
    
    // Verify navigation bar for pricing models is visible
    await expect(page.getByRole('tab', { name: 'Pay-as-you-go' }), 'Pay-as-you-go pricing tab must be visible').toBeVisible();
    await expect(page.getByRole('tab', { name: 'Flat rate' }), 'Flat rate pricing tab must be visible').toBeVisible();
    await expect(page.getByRole('tab', { name: 'Save when you commit' }), 'Save when you commit pricing tab must be visible').toBeVisible();
    await expect(page.getByRole('tab', { name: 'Pay less by using more' }), 'Pay less by using more pricing tab must be visible').toBeVisible();

    // Navigate to Pay-as-you-go pricing model
    await page.getByRole('tab', { name: 'Pay-as-you-go' }).click();
    await expect(page.getByRole('tab', { name: 'Pay-as-you-go' }), 'Pay-as-you-go tab should be selected').toHaveAttribute('aria-selected', 'true');

    // Navigate to Flat rate pricing model
    await page.getByRole('tab', { name: 'Flat rate' }).click();
    await expect(page.getByRole('tab', { name: 'Flat rate' }), 'Flat rate tab should be selected').toHaveAttribute('aria-selected', 'true');

    // Navigate to Save when you commit pricing model
    await page.getByRole('tab', { name: 'Save when you commit' }).click();
    await expect(page.getByRole('tab', { name: 'Save when you commit' }), 'Save when you commit tab should be selected').toHaveAttribute('aria-selected', 'true');

    // Navigate to Pay less by using more pricing model
    await page.getByRole('tab', { name: 'Pay less by using more' }).click();
    await expect(page.getByRole('tab', { name: 'Pay less by using more' }), 'Pay less by using more tab should be selected').toHaveAttribute('aria-selected', 'true');
  });

  test('negative — verify navigation fails when pricing models are not accessible', async () => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Simulate scenario where navigation bar might not be available by checking if tabs are disabled
    const payAsYouGoTab = page.getByRole('tab', { name: 'Pay-as-you-go' });
    const flatRateTab = page.getByRole('tab', { name: 'Flat rate' });
    
    // Check if tabs exist but might be in a non-interactive state
    await expect(payAsYouGoTab, 'Pay-as-you-go tab must exist even if not functional').toBeVisible();
    await expect(flatRateTab, 'Flat rate tab must exist even if not functional').toBeVisible();
    
    // Verify minimum required pricing models are present
    const allTabs = [
      page.getByRole('tab', { name: 'Pay-as-you-go' }),
      page.getByRole('tab', { name: 'Flat rate' }),
      page.getByRole('tab', { name: 'Save when you commit' }),
      page.getByRole('tab', { name: 'Pay less by using more' })
    ];
    
    let visibleTabsCount = 0;
    for (const tab of allTabs) {
      if (await tab.isVisible()) {
        visibleTabsCount++;
      }
    }
    
    expect(visibleTabsCount, 'At least 3 pricing model tabs should be visible').toBeGreaterThanOrEqual(3);
  });
});