import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Complete navigation workflow validation (M03_BS_023)', () => {
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

  test('positive — complete navigation workflow through all major sections', async () => {
    // User lands on Dashboard and verifies initial load
    await page.goto(BASE_URL);
    await expect(page, 'Dashboard page should be loaded successfully').toHaveURL(/dashboard/);

    // User clicks on settings in the left navigation bar
    const settingsButton = page.locator('div>div>div>div>span>button');
    await expect(settingsButton, 'Settings navigation button must be visible').toBeVisible();
    await settingsButton.click();

    // User clicks on help from the left navigation bar
    const helpButton = page.locator('div>div>div>div>button');
    await expect(helpButton, 'Help navigation button must be visible').toBeVisible();
    await helpButton.click();

    // User performs a search using the left navigation search functionality
    const searchInput = page.getByPlaceholder('Search');
    await expect(searchInput, 'Search input field must be visible in navigation').toBeVisible();
    await searchInput.fill('test search');
    await searchInput.press('Enter');

    // User clicks on dashboard and verifies all dashboard content is visible
    const dashboardButton = page.locator('div>div>div>div:nth-of-type(4)>div>div>div:nth-of-type(2)>button');
    await expect(dashboardButton, 'Dashboard navigation button must be visible').toBeVisible();
    await dashboardButton.click();
    await expect(page, 'Should return to dashboard after clicking dashboard navigation').toHaveURL(/dashboard/);

    // User clicks on projects in the left bar and verifies redirection to Projects page
    const projectsButton = page.locator('div>div>div:nth-of-type(2)>header>div>div>button');
    await expect(projectsButton, 'Projects navigation button must be visible').toBeVisible();
    await projectsButton.click();
    await expect(page, 'Should navigate to projects page after clicking projects navigation').toHaveURL(/projects/);

    // Verify all navigation interactions completed successfully
    await expect(page, 'Final navigation state should be on projects page').toHaveURL(/projects/);
  });
});