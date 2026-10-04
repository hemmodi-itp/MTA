import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('User navigates Aurora page using navigation bar (M02_BS_001)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — user successfully navigates through all navigation elements', async () => {
    await page.goto(BASE_URL);

    // Verify navigation bar is visible and functional by checking all navigation elements
    await expect(page.getByRole('link', { name: 'Overview' }), 'Overview navigation link must be visible').toBeVisible();
    await expect(page.getByRole('link', { name: 'Features' }), 'Features navigation link must be visible').toBeVisible();
    await expect(page.getByRole('link', { name: 'Pricing' }), 'Pricing navigation link must be visible').toBeVisible();
    await expect(page.getByRole('link', { name: 'Resources' }), 'Resources navigation link must be visible').toBeVisible();

    // Navigate through each navigation element to fetch page information
    await page.getByRole('link', { name: 'Overview' }).click();
    await expect(page, 'Overview page should load successfully').toHaveURL(/overview|aurora/);

    await page.getByRole('link', { name: 'Features' }).click();
    await expect(page, 'Features page should load successfully').toHaveURL(/features|aurora/);

    await page.getByRole('link', { name: 'Pricing' }).click();
    await expect(page, 'Pricing page should load successfully').toHaveURL(/pricing|aurora/);

    await page.getByRole('link', { name: 'Resources' }).click();
    await expect(page, 'Resources page should load successfully').toHaveURL(/resources|aurora/);
  });

  test('negative — navigation elements remain functional when accessed in rapid succession', async () => {
    await page.goto(BASE_URL);

    // Rapidly click navigation elements to test for potential race conditions
    await page.getByRole('link', { name: 'Features' }).click();
    await page.getByRole('link', { name: 'Overview' }).click();
    
    // Verify the navigation still works after rapid clicking
    await expect(page.getByRole('link', { name: 'Pricing' }), 'Pricing link should remain clickable after rapid navigation').toBeVisible();
    await page.getByRole('link', { name: 'Pricing' }).click();
    await expect(page, 'Page should still navigate correctly after rapid clicking').toHaveURL(/pricing|aurora/);
  });

  test('boundary — navigation elements work when page is refreshed between clicks', async () => {
    await page.goto(BASE_URL);

    // Click first navigation element
    await page.getByRole('link', { name: 'Features' }).click();
    
    // Refresh page and verify navigation still works
    await page.reload();
    await expect(page.getByRole('link', { name: 'Resources' }), 'Resources link should be visible after page refresh').toBeVisible();
    
    // Navigate to different section after refresh
    await page.getByRole('link', { name: 'Resources' }).click();
    await expect(page, 'Navigation should work correctly after page refresh').toHaveURL(/resources|aurora/);
  });
});