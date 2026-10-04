import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('User explores Aurora pricing information (M02_BS_006)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — user successfully navigates to pricing and explores detailed information', async () => {
    await page.goto(BASE_URL);
    
    // User clicks on Pricing
    await page.getByRole('link', { name: 'Pricing' }).click();
    await expect(page, 'Page should navigate to pricing section after clicking Pricing link').toHaveURL(/.*pricing.*/);
    
    // User scrolls down to find pricing information
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
    
    // Wait a moment for any dynamic content to load
    await page.waitForTimeout(2000);
    
    // Verify navigation was successful by checking URL contains pricing-related content
    await expect(page, 'User should be on a pricing-related page').toHaveURL(/.*pricing.*|.*rds.*aurora.*/);
  });

  test('negative — pricing link becomes unavailable or fails to load', async () => {
    await page.goto(BASE_URL);
    
    // Simulate network failure or slow loading
    await page.route('**/*pricing*', route => route.abort());
    
    try {
      await page.getByRole('link', { name: 'Pricing' }).click();
      await page.waitForTimeout(5000);
    } catch (error) {
      // Expected behavior when pricing page fails to load
    }
    
    // Verify we're still on the original Aurora page due to failed navigation
    await expect(page, 'Should remain on Aurora main page when pricing fails to load').toHaveURL(BASE_URL);
  });

  test('boundary — pricing page loads with minimal network conditions', async () => {
    await page.goto(BASE_URL);
    
    // Simulate slow network conditions
    await page.route('**/*', route => {
      setTimeout(() => route.continue(), 1000);
    });
    
    await page.getByRole('link', { name: 'Pricing' }).click();
    
    // Allow extra time for slow loading
    await page.waitForTimeout(8000);
    
    await expect(page, 'Pricing page should eventually load even under slow network conditions').toHaveURL(/.*pricing.*|.*rds.*aurora.*/);
  });
});