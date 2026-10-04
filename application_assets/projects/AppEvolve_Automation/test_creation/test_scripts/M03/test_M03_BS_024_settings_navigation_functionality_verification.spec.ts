import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Settings navigation functionality verification (M03_BS_024)', () => {
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

  test('positive — navigate to settings page through left navigation sidebar', async () => {
    await page.goto(BASE_URL);
    
    // Wait for dashboard page to load and left navigation to be visible
    await page.waitForLoadState('networkidle');
    
    // Verify the settings menu item is visible in the left navigation
    const settingsMenuItem = page.locator('div>div>div>div>span>button');
    await expect(settingsMenuItem, 'Settings menu item should be visible in left navigation').toBeVisible();
    
    // Click on the Settings menu item
    await settingsMenuItem.click();
    
    // Wait for navigation to complete
    await page.waitForLoadState('networkidle');
    
    // Verify that navigation to settings occurred by checking URL change
    await expect(page, 'Page URL should indicate navigation to settings section occurred').toHaveURL(/settings|configuration|preferences/);
  });
});