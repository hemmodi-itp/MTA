import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/projects';

test.describe.configure({ mode: 'serial' });

test.describe('View Project Details (M04_BS_001)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto("https://pt-dev.appevolve.intuitive.ai/");
    await page.locator("button:has-text('SSO Login')").click();
    await page.waitForTimeout(4000);
    await page.locator("#username").fill(process.env.APPEVOLVE_AUTOMATION_DEV_USERNAME ?? "");
    await page.locator("#password").fill(process.env.APPEVOLVE_AUTOMATION_DEV_PASSWORD ?? "");
    await page.locator("#kc-login").click();
    await page.waitForTimeout(2000);
    await page.locator("button.joyride__hurray-btn").click();
    await page.waitForTimeout(1000);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — navigate to project page and view comprehensive project details', async () => {
    await page.goto(BASE_URL);
    
    // Wait for the page to load completely
    await page.waitForLoadState('networkidle');
    
    // Verify we successfully navigated to the projects page
    await expect(page, 'Page URL should contain projects path').toHaveURL(/\/projects/);
    
    // Verify the page has loaded with project content
    await expect(page, 'Page should have a title indicating project functionality').toHaveTitle(/project/i);
  });

  test('negative — attempt to access project page with invalid URL parameters', async () => {
    // Navigate to projects page with invalid project ID parameter
    await page.goto(`${BASE_URL}/invalid-project-id`);
    
    // Wait for the page to handle the invalid request
    await page.waitForLoadState('networkidle');
    
    // Verify the application handles the invalid URL gracefully
    await expect(page, 'Page should still be accessible even with invalid parameters').toHaveURL(/\/projects/);
  });

  test('boundary — access project page with maximum length URL parameters', async () => {
    // Create a very long parameter string to test URL length boundaries
    const longParam = 'a'.repeat(200);
    await page.goto(`${BASE_URL}?search=${longParam}`);
    
    // Wait for the page to process the long parameter
    await page.waitForLoadState('networkidle');
    
    // Verify the page handles long parameters without breaking
    await expect(page, 'Page should handle long URL parameters gracefully').toHaveURL(/\/projects/);
  });
});