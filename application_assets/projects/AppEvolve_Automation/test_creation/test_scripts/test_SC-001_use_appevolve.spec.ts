import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Use AppEvolve (SC-001)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — user can successfully enter search term in search field', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load and search field to be available
    await expect(page.getByPlaceholder('Search'), 'Search input field should be visible').toBeVisible();
    
    // Enter search term in the input field
    await page.getByPlaceholder('Search').fill('project management dashboard');
    
    // Verify the search term was entered successfully
    await expect(page.getByPlaceholder('Search'), 'Search input should contain the entered search term').toHaveValue('project management dashboard');
  });
});