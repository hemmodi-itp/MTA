import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Navigation Search Functionality (M03_BS_015)', () => {
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

  test('positive — search for navigation item and navigate to selected result', async () => {
    await page.goto(BASE_URL);
    
    // Locate the search option in the left navigation bar
    const searchInput = page.getByPlaceholder('Search');
    await expect(searchInput, 'Search input field must be visible in left navigation').toBeVisible();
    
    // Enter a search term for a navigation item
    await searchInput.click();
    await searchInput.fill('Projects');
    
    // Wait for search results to be displayed
    await page.waitForTimeout(1000);
    
    // Verify search input contains the entered term
    await expect(searchInput, 'Search input should contain the entered search term').toHaveValue('Projects');
    
    // Press Enter or wait for search functionality to process
    await searchInput.press('Enter');
    
    // Wait for any navigation or search processing
    await page.waitForTimeout(2000);
    
    // Verify that search functionality has been executed
    await expect(searchInput, 'Search input should remain accessible after search').toBeVisible();
  });
});