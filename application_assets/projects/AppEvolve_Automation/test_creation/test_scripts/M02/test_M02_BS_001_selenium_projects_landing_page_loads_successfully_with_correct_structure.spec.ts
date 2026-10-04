import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Selenium Projects landing page loads successfully with correct structure (M02_BS_001)', () => {
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

  test('positive — Selenium Projects landing page loads with correct structure and no errors', async () => {
    // Set up console error tracking
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Navigate to the Selenium Projects landing page
    const response = await page.goto(BASE_URL);
    
    // Verify page returns HTTP 200 status
    await expect(response?.status(), 'Page should return HTTP 200 status').toBe(200);
    
    // Wait for page to fully load
    await page.waitForLoadState('networkidle');
    
    // Confirm page title contains both 'Selenium' and 'Projects'
    const title = await page.title();
    await expect(title, 'Page title should contain "Selenium"').toContain('Selenium');
    await expect(title, 'Page title should contain "Projects"').toContain('Projects');
    
    // Check that no console errors are present
    await expect(consoleErrors.length, 'Page should load without console errors').toBe(0);
  });
});