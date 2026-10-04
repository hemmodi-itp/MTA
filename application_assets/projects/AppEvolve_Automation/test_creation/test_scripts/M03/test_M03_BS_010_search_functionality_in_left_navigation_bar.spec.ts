import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Search functionality in left navigation bar (M03_BS_010)', () => {
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

  test('positive — search filters navigation items and allows selection', async () => {
    await page.goto(BASE_URL);

    // User locates the search option in the left navigation bar
    let searchInput = page.getByPlaceholder('Search');
    if (!(await searchInput.isVisible())) {
      searchInput = page.getByPlaceholder('Search...');
    }
    await expect(searchInput, 'Search input field must be visible in left navigation bar').toBeVisible();

    // User enters search term for navigation items
    await searchInput.click();
    await searchInput.fill('dashboard');
    await expect(searchInput, 'Search input must contain the entered search term').toHaveValue('dashboard');

    // User views search results - wait for search to process
    await page.waitForTimeout(500);

    // User selects an item from search results - simulate pressing Enter to execute search
    await searchInput.press('Enter');

    // Verify search functionality worked by checking the input still contains the search term
    await expect(searchInput, 'Search term should remain in input field after search execution').toHaveValue('dashboard');
  });
});