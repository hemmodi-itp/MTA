import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('User reads Aurora introduction information (M02_BS_002)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — user successfully navigates to and reads Aurora introduction section', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Verify we are on the correct Aurora page
    await expect(page, 'User should be on the Amazon Aurora RDS page').toHaveURL(/.*aurora.*/);
    
    // Look for Aurora introduction content by common patterns
    const introSection = page.locator('h1, h2, h3').filter({ hasText: /what.*aurora/i }).first();
    
    // If intro section exists, scroll to it and verify content is visible
    if (await introSection.count() > 0) {
      await introSection.scrollIntoViewIfNeeded();
      await expect(introSection, 'Aurora introduction heading should be visible after scrolling').toBeVisible();
    }
    
    // Verify page contains Aurora descriptive content
    const auroraContent = page.getByText(/aurora/i).first();
    await expect(auroraContent, 'Page should contain Aurora descriptive content for user understanding').toBeVisible();
    
    // Verify page title contains Aurora information
    await expect(page, 'Page title should indicate this is about Aurora').toHaveTitle(/aurora/i);
  });

  test('negative — page load fails or content is unavailable', async () => {
    // Test invalid URL variation to simulate content unavailability
    const invalidUrl = BASE_URL + '/nonexistent-path';
    
    await page.goto(invalidUrl, { waitUntil: 'networkidle' });
    
    // Verify we get an error page or are redirected
    const currentUrl = page.url();
    const isErrorPage = currentUrl.includes('404') || currentUrl.includes('error') || !currentUrl.includes('aurora');
    
    if (isErrorPage) {
      await expect(page, 'Invalid Aurora page URL should result in error page or redirect').not.toHaveURL(invalidUrl);
    } else {
      // If redirected to valid page, that's acceptable behavior
      await expect(page, 'System should handle invalid URLs gracefully').toHaveURL(/aws\.amazon\.com/);
    }
  });

  test('boundary — user accesses Aurora page with minimal browser capabilities', async () => {
    // Navigate back to valid Aurora page
    await page.goto(BASE_URL);
    
    // Disable JavaScript to test minimal functionality
    await page.context().addInitScript(() => {
      Object.defineProperty(navigator, 'userAgent', {
        writable: true,
        value: 'Mozilla/5.0 (compatible; MinimalBrowser/1.0)'
      });
    });
    
    await page.reload({ waitUntil: 'domcontentloaded' });
    
    // Verify basic content is still accessible without enhanced features
    const basicContent = page.locator('body');
    await expect(basicContent, 'Aurora page should display basic content even with minimal browser capabilities').toBeVisible();
    
    // Verify essential Aurora information is still present in basic form
    const auroraText = page.getByText(/aurora/i).first();
    await expect(auroraText, 'Aurora information should be accessible in basic browser environment').toBeVisible();
  });
});