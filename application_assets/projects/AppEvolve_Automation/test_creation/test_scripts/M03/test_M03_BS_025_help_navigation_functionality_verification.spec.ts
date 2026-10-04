import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Help navigation functionality verification (M03_BS_025)', () => {
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

  test('positive — user can successfully access help documentation through left navigation', async () => {
    // Navigate to dashboard page
    await page.goto(BASE_URL);
    
    // Wait for page to load and left navigation to be available
    await page.waitForLoadState('networkidle');
    
    // Verify Help menu item is visible in left navigation
    const helpMenuItem = page.locator('div>div>div>div>button');
    await expect(helpMenuItem, 'Help menu item must be visible in left navigation sidebar').toBeVisible();
    
    // Click on the Help menu item
    await helpMenuItem.click();
    
    // Wait for navigation to complete
    await page.waitForLoadState('networkidle');
    
    // Verify that help content or help page is accessible
    // Since we can only verify navigation occurred, check URL changed or page responded
    await expect(page, 'Page should respond after clicking help menu item').not.toHaveURL(BASE_URL);
  });
});