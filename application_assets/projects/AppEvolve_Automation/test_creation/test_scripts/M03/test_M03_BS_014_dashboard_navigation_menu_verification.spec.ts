import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Dashboard Navigation Menu Verification (M03_BS_014)', () => {
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

  test('positive — all navigation menu items are visible and clickable in left sidebar', async () => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Verify search navigation item is present and visible
    await expect(page.getByPlaceholder('Search'), 'Search navigation item must be visible in the sidebar').toBeVisible();

    // Verify navigation menu item buttons are present and visible
    await expect(page.locator('div>div>div>div>span>button'), 'Navigation menu item buttons must be visible in the sidebar').toBeVisible();
    await expect(page.locator('div>div>div>div>button'), 'Clickable navigation menu items must be visible in the sidebar').toBeVisible();
    await expect(page.locator('div>div>div>div:nth-of-type(4)>div>div>div:nth-of-type(2)>button'), 'Dashboard navigation item must be visible in the sidebar').toBeVisible();

    // Test clickability of search functionality
    await expect(page.getByPlaceholder('Search'), 'Search input must be clickable').toBeEnabled();
    await page.getByPlaceholder('Search').click();

    // Test clickability of navigation menu item buttons
    const navButton = page.locator('div>div>div>div>span>button').first();
    await expect(navButton, 'Navigation menu item button must be clickable').toBeEnabled();
    await navButton.click();

    // Test clickability of general navigation items
    const clickableNavItem = page.locator('div>div>div>div>button').first();
    await expect(clickableNavItem, 'General navigation item must be clickable').toBeEnabled();
    await clickableNavItem.click();

    // Test clickability of dashboard navigation item specifically
    const dashboardNavItem = page.locator('div>div>div>div:nth-of-type(4)>div>div>div:nth-of-type(2)>button');
    await expect(dashboardNavItem, 'Dashboard navigation item must be clickable').toBeEnabled();
    await dashboardNavItem.click();

    // Verify that clicking navigation items responds appropriately by checking URL changes or staying on dashboard
    await expect(page, 'Navigation interactions should maintain proper URL context').toHaveURL(/.*dashboard.*/);
  });
});