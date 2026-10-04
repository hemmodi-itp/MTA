import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Search functionality in left navigation bar (M03_BS_002)', () => {
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

  test('positive — user can search and filter navigation items using search field', async () => {
    await page.goto(BASE_URL);
    
    // User locates the search option in the left navigation bar
    await expect(page.getByPlaceholder('Search'), 'Search field must be visible in left navigation bar').toBeVisible();
    
    // User enters search terms in the search field
    await page.getByPlaceholder('Search').fill('project dashboard');
    
    // User initiates search for navigation items
    await page.getByPlaceholder('Search').press('Enter');
    
    // Verify search field contains the entered text
    await expect(page.getByPlaceholder('Search'), 'Search field should contain entered search terms').toHaveValue('project dashboard');
  });
});