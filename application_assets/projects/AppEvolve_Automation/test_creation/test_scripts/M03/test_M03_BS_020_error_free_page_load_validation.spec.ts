import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Error-Free Page Load Validation (M03_BS_020)', () => {
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

  test('positive — dashboard loads without console errors', async () => {
    // Clear browser console to start with clean state
    await page.evaluate(() => console.clear());
    
    // Set up console error monitoring
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Set up page error monitoring for unhandled JavaScript errors
    const pageErrors: string[] = [];
    page.on('pageerror', error => {
      pageErrors.push(error.message);
    });

    // Navigate to the dashboard page
    await page.goto(BASE_URL);

    // Wait for complete page load by checking document ready state and network idle
    await page.waitForLoadState('domcontentloaded');
    await page.waitForLoadState('networkidle');

    // Additional wait to ensure all JavaScript has executed
    await page.waitForTimeout(2000);

    // Verify no console errors occurred during page load
    await expect(consoleErrors.length, 'Dashboard should load without console errors').toBe(0);

    // Verify no JavaScript errors occurred during page load  
    await expect(pageErrors.length, 'Dashboard should load without JavaScript errors').toBe(0);

    // Verify page loaded successfully by checking the URL
    await expect(page, 'Dashboard URL should be loaded correctly').toHaveURL(BASE_URL);

    // Verify page is in ready state
    const readyState = await page.evaluate(() => document.readyState);
    await expect(readyState, 'Document should be in complete ready state').toBe('complete');
  });
});