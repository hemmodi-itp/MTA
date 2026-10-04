import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('Browse AWS_Test (SC-003)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — navigate through AWS_Test interface controls', async () => {
    await page.goto(BASE_URL);
    
    // Click the filter all
    await page.getByRole('button', { name: 'Filter: All' }).click();
    await expect(page.getByRole('button', { name: 'Filter: All' }), 'Filter All button should remain accessible after click').toBeVisible();
    
    // Click the skip backward
    await page.getByRole('button', { name: 'Skip Backward' }).click();
    await expect(page.getByRole('button', { name: 'Skip Backward' }), 'Skip Backward button should remain accessible after click').toBeVisible();
    
    // Click the playback rate
    await page.getByRole('button', { name: 'Playback Rate' }).click();
    await expect(page.getByRole('button', { name: 'Playback Rate' }), 'Playback Rate button should remain accessible after click').toBeVisible();
    
    // Click the back to top
    await page.getByRole('button', { name: 'Back to top' }).click();
    await expect(page.getByRole('button', { name: 'Back to top' }), 'Back to top button should remain accessible after click').toBeVisible();
    
    // Click the AWS sales representative connection button
    await page.getByRole('button', { name: 'I can connect you with an AWS sales representative if you like to learn more about our products and services.' }).click();
    await expect(page.getByRole('button', { name: 'I can connect you with an AWS sales representative if you like to learn more about our products and services.' }), 'AWS sales representative button should remain accessible after click').toBeVisible();
  });

  test('negative — interface controls fail to respond', async () => {
    await page.goto(BASE_URL);
    
    // Attempt to interact with controls when they might be disabled or non-functional
    try {
      await page.getByRole('button', { name: 'Filter: All' }).click({ timeout: 1000 });
    } catch (error) {
      await expect(page.getByRole('button', { name: 'Filter: All' }), 'Filter All button should be visible even if not functional').toBeVisible();
    }
    
    // Verify page remains on expected URL even when controls might not work as expected
    await expect(page, 'Page should remain on Aurora RDS page when controls fail').toHaveURL(/aws\.amazon\.com\/rds\/aurora/);
  });

  test('boundary — rapid sequential clicks on interface controls', async () => {
    await page.goto(BASE_URL);
    
    // Test rapid sequential clicking to check interface stability
    const filterButton = page.getByRole('button', { name: 'Filter: All' });
    const skipButton = page.getByRole('button', { name: 'Skip Backward' });
    
    // Rapid clicks to test boundary behavior
    await filterButton.click();
    await skipButton.click();
    await filterButton.click();
    
    // Verify both buttons remain functional after rapid interaction
    await expect(filterButton, 'Filter All button should remain stable after rapid clicks').toBeVisible();
    await expect(skipButton, 'Skip Backward button should remain stable after rapid clicks').toBeVisible();
  });
});