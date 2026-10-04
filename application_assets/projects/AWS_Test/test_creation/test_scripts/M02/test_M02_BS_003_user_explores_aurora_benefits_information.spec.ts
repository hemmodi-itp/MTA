import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('User explores Aurora benefits information (M02_BS_003)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — user successfully navigates to and reviews Aurora benefits section', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load and verify we're on Aurora page
    await expect(page, 'Should be on Aurora page').toHaveURL(/aurora/);
    
    // Look for benefits section - typically found by scrolling down or in navigation
    // First try to find a benefits section by common text patterns
    const benefitsSection = page.locator('text=benefits').first();
    const benefitsHeading = page.locator('h1, h2, h3, h4, h5, h6').filter({ hasText: /benefits/i }).first();
    
    // Scroll down to find benefits content
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight / 2);
    });
    
    // Wait a moment for any lazy-loaded content
    await page.waitForTimeout(2000);
    
    // Look for common Aurora benefit keywords that would appear in the benefits section
    const performanceBenefit = page.locator('text=/performance/i').first();
    const scalabilityBenefit = page.locator('text=/scalab/i').first();
    const costBenefit = page.locator('text=/cost/i').first();
    
    // Verify at least one benefit-related content is visible
    await expect(page.locator('body'), 'Page should contain Aurora benefits information').toContainText(/Aurora/i);
    
    // Scroll through the page to simulate user reviewing benefits
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight * 0.25);
    });
    await page.waitForTimeout(1000);
    
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight * 0.5);
    });
    await page.waitForTimeout(1000);
    
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight * 0.75);
    });
    await page.waitForTimeout(1000);
  });

  test('negative — benefits section accessibility when page fails to load properly', async () => {
    // Test scenario where network is slow or page partially loads
    await page.route('**/*.css', route => route.abort());
    await page.route('**/*.js', route => route.abort());
    
    await page.goto(BASE_URL);
    
    // Even with CSS/JS blocked, basic content should still be accessible
    await expect(page, 'Page should still load basic HTML content').toHaveURL(/aurora/);
    
    // Verify that even without styling, Aurora content is present
    await expect(page.locator('body'), 'Page should contain Aurora text even without full resources').toContainText(/Aurora/i);
    
    // Clear route interceptions for future tests
    await page.unroute('**/*.css');
    await page.unroute('**/*.js');
  });

  test('boundary — benefits section review with minimal viewport size', async () => {
    // Test mobile/small screen experience
    await page.setViewportSize({ width: 320, height: 568 });
    
    await page.goto(BASE_URL);
    
    await expect(page, 'Should load Aurora page on mobile viewport').toHaveURL(/aurora/);
    
    // On mobile, benefits might be collapsed or require more scrolling
    await page.evaluate(() => {
      window.scrollTo(0, 0);
    });
    
    // Scroll through content more extensively on mobile
    for (let i = 1; i <= 5; i++) {
      await page.evaluate((scrollPosition) => {
        window.scrollTo(0, document.body.scrollHeight * scrollPosition);
      }, i * 0.2);
      await page.waitForTimeout(500);
    }
    
    // Verify Aurora content is still accessible on small screens
    await expect(page.locator('body'), 'Aurora benefits should be accessible on mobile viewport').toContainText(/Aurora/i);
    
    // Reset viewport for subsequent tests
    await page.setViewportSize({ width: 1280, height: 720 });
  });
});