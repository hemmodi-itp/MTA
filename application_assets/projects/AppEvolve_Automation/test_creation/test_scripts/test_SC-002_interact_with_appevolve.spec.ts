import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Interact with AppEvolve (SC-002)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — complete interaction flow with all dashboard elements', async () => {
    await page.goto(BASE_URL);
    
    // Click the tour button
    await page.getByRole('button', { name: 'Tour' }).click();
    await expect(page.getByRole('button', { name: 'Tour' }), 'Tour button should remain visible after click').toBeVisible();
    
    // Click the users total button
    await page.getByRole('button', { name: 'Users3Total' }).click();
    await expect(page.getByRole('button', { name: 'Users3Total' }), 'Users total button should remain clickable').toBeVisible();
    
    // Click the clients total button
    await page.getByRole('button', { name: 'Clients2Total' }).click();
    await expect(page.getByRole('button', { name: 'Clients2Total' }), 'Clients total button should remain clickable').toBeVisible();
    
    // Click the projects total button
    await page.getByRole('button', { name: 'Projects143Total' }).click();
    await expect(page.getByRole('button', { name: 'Projects143Total' }), 'Projects total button should remain clickable').toBeVisible();
    
    // Click the profiles total button
    await page.getByRole('button', { name: 'Profiles0Total' }).click();
    await expect(page.getByRole('button', { name: 'Profiles0Total' }), 'Profiles total button should remain clickable').toBeVisible();
    
    // Click available project buttons
    await page.getByRole('button', { name: 'proj-190' }).click();
    await expect(page.getByRole('button', { name: 'proj-190' }), 'Project 190 button should remain clickable').toBeVisible();
    
    await page.getByRole('button', { name: 'proj-194' }).click();
    await expect(page.getByRole('button', { name: 'proj-194' }), 'Project 194 button should remain clickable').toBeVisible();
    
    // Verify URL remains on dashboard after all interactions
    await expect(page, 'Should remain on dashboard after all interactions').toHaveURL(/dashboard/);
  });
});