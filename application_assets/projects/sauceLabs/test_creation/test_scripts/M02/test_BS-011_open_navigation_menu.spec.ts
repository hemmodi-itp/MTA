import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Open Navigation Menu (BS-011)', () => {
  

  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — hamburger menu opens and displays navigation options', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click on the hamburger menu icon in the header
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Verify the sidebar menu opens and displays navigation options
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must be visible in opened menu').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must be visible in opened menu').toBeVisible();
  });

  test('negative — menu button remains functional when clicked multiple times rapidly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Rapidly click menu button multiple times
    const menuButton = page.getByRole('button', { name: 'Open Menu' });
    await menuButton.click();
    await menuButton.click();
    await menuButton.click();
    
    // Verify menu still displays navigation options correctly
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must remain visible after rapid clicks').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must remain visible after rapid clicks').toBeVisible();
  });

  test('negative — menu functionality works with special characters in URL parameters', async ({ page }) => {
    await page.goto(`${BASE_URL}?test=%3Cscript%3Ealert('xss')%3C/script%3E`);
    
    // Click hamburger menu with special characters in URL
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Verify menu opens normally despite URL manipulation
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must be visible even with special chars in URL').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must be visible even with special chars in URL').toBeVisible();
  });

  test('negative — menu opens correctly after page refresh', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Refresh page and immediately try to open menu
    await page.reload();
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Verify menu functionality persists after refresh
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must be visible after page refresh').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must be visible after page refresh').toBeVisible();
  });

  test('negative — menu button works when accessed via keyboard navigation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to menu button using keyboard and activate
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');
    
    // Verify menu opens via keyboard interaction
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must be visible when menu opened via keyboard').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must be visible when menu opened via keyboard').toBeVisible();
  });

  test('boundary — menu functionality at minimum viewport width', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(BASE_URL);
    
    // Click menu button at minimum viewport
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Verify menu displays correctly at minimum width
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must be visible at minimum viewport width').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must be visible at minimum viewport width').toBeVisible();
  });

  test('boundary — menu functionality at maximum typical viewport width', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(BASE_URL);
    
    // Click menu button at maximum viewport
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Verify menu displays correctly at maximum width
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must be visible at maximum viewport width').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must be visible at maximum viewport width').toBeVisible();
  });

  test('boundary — menu opens correctly with very long URL path', async ({ page }) => {
    const longPath = 'a'.repeat(2000);
    await page.goto(`${BASE_URL}?path=${longPath}`);
    
    // Click menu button with extremely long URL
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Verify menu functionality with long URL parameters
    await expect(page.getByRole('link', { name: 'All Items' }), 'All Items navigation option must be visible with very long URL parameters').toBeVisible();
    await expect(page.getByRole('link', { name: 'About' }), 'About navigation option must be visible with very long URL parameters').toBeVisible();
  });

});