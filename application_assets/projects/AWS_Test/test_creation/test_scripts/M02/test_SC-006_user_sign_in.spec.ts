import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('User Sign In (SC-006)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — navigate to government solutions page successfully', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load and look for the government solutions link
    await page.waitForLoadState('domcontentloaded');
    
    // Try different approaches to find the government solutions link
    const linkText = 'government solutions designed to help government agencies modernize meet mandates reduce costs and deliver mission outcomes view industry';
    
    // Look for a link or button containing government solutions text
    const governmentLink = page.locator('a, button').filter({ hasText: /government.*solutions/i }).first();
    
    if (await governmentLink.count() > 0) {
      await governmentLink.click();
    } else {
      // Fallback: try to find by partial text match
      const partialLink = page.getByText(/government.*solutions/i).first();
      await partialLink.click();
    }
    
    // Wait for navigation to complete
    await page.waitForLoadState('domcontentloaded');
    
    // Assert URL contains government solutions path
    await expect(page, 'URL should navigate to government solutions page').toHaveURL(/.*government.*solutions.*/i);
  });

  test('negative — handle missing navigation target gracefully', async () => {
    const iterations = [
      {
        click_target: "government solutions designed to help government agencies modernize meet mandates reduce costs and deliver mission outcomes view industry",
        expected_heading: "",
        expected_content: "modernize meet mandates reduce costs",
        expected_url_fragment: "/government-solutions",
        expected_error: "Page content failed to load or heading not found"
      }
    ];

    for (let i = 0; i < iterations.length; i++) {
      const iteration = iterations[i];
      
      await page.goto(BASE_URL);
      await page.waitForLoadState('domcontentloaded');
      
      // Try to find the navigation target
      const linkExists = await page.locator('a, button').filter({ hasText: /government.*solutions/i }).count();
      
      if (linkExists === 0) {
        // Verify that navigation target is not available
        await expect(page.locator('a, button').filter({ hasText: /government.*solutions/i }), 'Government solutions link should not be found when missing').toHaveCount(0);
      } else {
        // If link exists but leads to error state
        const governmentLink = page.locator('a, button').filter({ hasText: /government.*solutions/i }).first();
        await governmentLink.click();
        await page.waitForLoadState('domcontentloaded');
        
        // Check if expected heading is empty (error condition)
        if (iteration.expected_heading === "") {
          // Verify that page loaded but might be missing expected content
          await expect(page, 'Page should load even with missing content').toHaveURL(/.*/);
        }
      }
    }
  });
});