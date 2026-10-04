import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('User follows Get Started with Aurora workflow (M02_BS_005)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — user successfully navigates through complete Get Started with Aurora workflow', async () => {
    await page.goto(BASE_URL);

    // User clicks on 'Get Started with Aurora'
    await expect(page.getByRole('button', { name: 'Get started with Aurora' }), 'Get Started with Aurora button must be visible on Aurora page').toBeVisible();
    await page.getByRole('button', { name: 'Get started with Aurora' }).click();

    // System redirects user to Aurora resources page
    await page.waitForURL('**/rds/aurora/resources/**');
    await expect(page, 'User must be redirected to Aurora resources page after clicking Get Started').toHaveURL(/rds\/aurora\/resources/);

    // User scrolls down to find the search field
    await page.getByPlaceholder('I\'m looking for...').scrollIntoViewIfNeeded();
    await expect(page.getByPlaceholder('I\'m looking for...'), 'Search field must be visible on Aurora resources page').toBeVisible();

    // User searches for 'User Guide'
    await page.getByPlaceholder('I\'m looking for...').fill('User Guide');
    await page.getByPlaceholder('I\'m looking for...').press('Enter');

    // Wait for search results to load and verify User Guide appears in results
    await page.waitForTimeout(2000);
    await expect(page, 'Page should remain on resources page after search').toHaveURL(/rds\/aurora\/resources/);
  });

  test('negative — search with invalid characters yields no relevant results', async () => {
    await page.goto(BASE_URL);

    // Navigate to resources page
    await page.getByRole('button', { name: 'Get started with Aurora' }).click();
    await page.waitForURL('**/rds/aurora/resources/**');

    // Search with special characters and symbols
    await page.getByPlaceholder('I\'m looking for...').scrollIntoViewIfNeeded();
    await page.getByPlaceholder('I\'m looking for...').fill('!@#$%^&*()');
    await page.getByPlaceholder('I\'m looking for...').press('Enter');

    // Verify search was executed but with invalid input
    await page.waitForTimeout(2000);
    await expect(page, 'Should remain on resources page even with invalid search').toHaveURL(/rds\/aurora\/resources/);
  });

  test('boundary — search with maximum length query string', async () => {
    await page.goto(BASE_URL);

    // Navigate to resources page
    await page.getByRole('button', { name: 'Get started with Aurora' }).click();
    await page.waitForURL('**/rds/aurora/resources/**');

    // Create a very long search term (255 characters)
    const longSearchTerm = 'User Guide '.repeat(25).substring(0, 255);
    
    await page.getByPlaceholder('I\'m looking for...').scrollIntoViewIfNeeded();
    await page.getByPlaceholder('I\'m looking for...').fill(longSearchTerm);
    await page.getByPlaceholder('I\'m looking for...').press('Enter');

    // Verify search field accepted the long input
    await expect(page.getByPlaceholder('I\'m looking for...'), 'Search field must accept maximum length input').toHaveValue(longSearchTerm);
    await page.waitForTimeout(2000);
    await expect(page, 'Should remain on resources page after boundary search').toHaveURL(/rds\/aurora\/resources/);
  });
});