import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Navigate through left sidebar menu items (M03_BS_001)', () => {
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

  test('positive — navigate through all left sidebar menu items successfully', async () => {
    await page.goto(BASE_URL);
    
    // Verify initial dashboard state - check that navigation elements are visible
    await expect(page.getByRole('button', { name: 'Tour' }), 'Tour button should be visible in left navigation').toBeVisible();
    await expect(page.getByRole('button', { name: 'Projects\n\n143\n\nTotal' }), 'Projects navigation item should be visible in left sidebar').toBeVisible();
    await expect(page.getByRole('button', { name: 'Users\n\n3\n\nTotal' }), 'Users dashboard component should be visible').toBeVisible();
    
    // User clicks on Help (Tour) from the left navigation bar
    await page.getByRole('button', { name: 'Tour' }).click();
    await expect(page.getByRole('button', { name: 'Tour' }), 'Tour button should remain accessible after click').toBeVisible();
    
    // User clicks on Dashboard and views dashboard content
    await page.getByRole('button', { name: 'Users\n\n3\n\nTotal' }).click();
    await expect(page.getByRole('button', { name: 'Users\n\n3\n\nTotal' }), 'Users dashboard component should be accessible').toBeVisible();
    
    // User clicks on Projects in the left navigation bar
    await page.getByRole('button', { name: 'Projects\n\n143\n\nTotal' }).click();
    await expect(page.getByRole('button', { name: 'Projects\n\n143\n\nTotal' }), 'Projects navigation item should be accessible after click').toBeVisible();
    
    // Verify search functionality is available in navigation
    await expect(page.getByPlaceholder('Search'), 'Search option should be available in left navigation bar').toBeVisible();
  });
});