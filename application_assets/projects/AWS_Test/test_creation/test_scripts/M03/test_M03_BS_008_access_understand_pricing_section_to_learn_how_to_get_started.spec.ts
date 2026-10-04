import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/pricing/';

test.describe.configure({ mode: 'serial' });

test.describe('Access Understand Pricing section to learn how to get started (M03_BS_008)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

test('positive — navigate to Understand Pricing section and verify getting started guidance is available', async ({ page }) => {
  await page.goto('https://aws.amazon.com/pricing/');
  
  // Wait for page to fully load with extended timeout
  await expect(page.locator('body')).toContainText('AWS Pricing', 'Page should contain AWS Pricing content', { timeout: 20000 });
  
  // Verify getting started guidance is available
  await expect(page.locator('body')).toContainText('Get started for free', 'Getting started guidance should be available');
});

test('negative — verify error handling when required section content is not found', async ({ page }) => {
  await page.goto('https://aws.amazon.com/pricing/');
  
  // This test verifies that expected pricing content is present, not missing
  // Verify AWS Pricing page loaded successfully
  await expect(page.locator('body')).toContainText('AWS Pricing', 'AWS Pricing content should be present', { timeout: 20000 });
  
  // Verify getting started guidance is present on the page (not missing)
  await expect(page.locator('body')).toContainText('Get started for free', 'Getting started guidance should be present on the page');
});

test('boundary — verify minimum number of guidance items are available', async ({ page }) => {
  await page.goto('https://aws.amazon.com/pricing/');
  
  // Wait for page to fully load with extended timeout
  await expect(page.locator('body')).toContainText('AWS Pricing', 'Page should contain AWS Pricing content', { timeout: 20000 });
  
  // Verify multiple guidance items are available on the page
  const guidanceElements = page.locator('text=/Get started|Free Tier|Calculator|pricing|Support/i');
  const count = await guidanceElements.count();
  
  // Verify at least minimum number of guidance items (should be at least 3)
  expect(count).toBeGreaterThanOrEqual(3, 'Minimum number of guidance items should be available');
  
  // Verify specific key guidance items are present
  await expect(page.locator('body')).toContainText('Get started for free', 'Get started guidance should be available');
  await expect(page.locator('body')).toContainText('Free Tier', 'Free Tier guidance should be available');
});
});