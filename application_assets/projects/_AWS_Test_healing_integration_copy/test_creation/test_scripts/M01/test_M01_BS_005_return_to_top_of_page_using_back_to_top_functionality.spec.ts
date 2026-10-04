import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/';

test.describe.configure({ mode: 'serial' });

test.describe('Return to top of page using back to top functionality (M01_BS_005)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — scrolling to bottom and using back to top button returns user to page header', async () => {
    await page.goto(BASE_URL);
    
    // Get initial scroll position (should be 0 at top)
    const initialScrollY = await page.evaluate(() => window.scrollY);
    await expect(initialScrollY, 'Page should start at the top').toBe(0);
    
    // Scroll down to the bottom of the page
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Wait for scroll to complete and verify we're at the bottom
    await page.waitForTimeout(500);
    const bottomScrollY = await page.evaluate(() => window.scrollY);
    await expect(bottomScrollY, 'Page should be scrolled down from initial position').toBeGreaterThan(100);
    
    // Locate and verify the back to top button is visible
    const backToTopButton = page.getByRole('button', { name: 'Back to top' });
    await expect(backToTopButton, 'Back to top button should be visible after scrolling down').toBeVisible();
    
    // Click on the back to top button
    await backToTopButton.click();
    
    // Wait for scroll animation to complete
    await page.waitForTimeout(1000);
    
    // Verify user is taken back to the top of the page
    const finalScrollY = await page.evaluate(() => window.scrollY);
    await expect(finalScrollY, 'Page should return to top position after clicking back to top button').toBe(0);
  });

  test('negative — back to top button should not be visible when already at page top', async () => {
    await page.goto(BASE_URL);
    
    // Ensure we're at the top of the page
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(500);
    
    // Verify we're at the top
    const scrollY = await page.evaluate(() => window.scrollY);
    await expect(scrollY, 'Page should be at the top').toBe(0);
    
    // Back to top button should not be visible when at the top
    const backToTopButton = page.getByRole('button', { name: 'Back to top' });
    await expect(backToTopButton, 'Back to top button should not be visible when already at page top').not.toBeVisible();
  });

  test('boundary — back to top button functionality when scrolled minimally', async () => {
    await page.goto(BASE_URL);
    
    // Scroll down just a small amount (boundary case)
    await page.evaluate(() => window.scrollTo(0, 100));
    await page.waitForTimeout(500);
    
    // Verify minimal scroll position
    const minimalScrollY = await page.evaluate(() => window.scrollY);
    await expect(minimalScrollY, 'Page should be scrolled down minimally').toBeGreaterThan(50);
    
    // Check if back to top button is available (may or may not be visible at minimal scroll)
    const backToTopButton = page.getByRole('button', { name: 'Back to top' });
    
    // If button is visible, test its functionality
    if (await backToTopButton.isVisible()) {
      await backToTopButton.click();
      await page.waitForTimeout(1000);
      
      const finalScrollY = await page.evaluate(() => window.scrollY);
      await expect(finalScrollY, 'Page should return to top even from minimal scroll position').toBe(0);
    }
  });
});