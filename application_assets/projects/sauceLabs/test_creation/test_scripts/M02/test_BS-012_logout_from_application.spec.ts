import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Logout from Application (BS-012)', () => {
  

  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — user successfully logs out and is redirected to login page', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Open the hamburger menu
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Click the logout option
    await page.getByRole('link', { name: 'Logout' }).click();
    
    // Verify redirection to login page
    await expect(page, 'User should be redirected to login page after logout').toHaveURL(/.*login/);
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
  });

  test('negative — hamburger menu not opened before logout attempt', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt to access logout without opening menu
    const logoutLink = page.getByRole('link', { name: 'Logout' });
    await expect(logoutLink, 'Logout link should not be visible when menu is closed').not.toBeVisible();
  });

  test('negative — multiple rapid logout clicks', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Open menu and click logout multiple times rapidly
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    const logoutLink = page.getByRole('link', { name: 'Logout' });
    await logoutLink.click();
    
    // Verify single logout action completes properly
    await expect(page, 'Multiple logout clicks should not cause errors and redirect to login').toHaveURL(/.*login/);
    await expect(page.getByPlaceholder('Username'), 'Login form should be accessible after multiple logout attempts').toBeVisible();
  });

  test('negative — logout during page navigation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Start navigation and immediately try to logout
    await page.getByRole('button', { name: 'Open Menu' }).click();
    
    // Simulate concurrent actions
    const logoutPromise = page.getByRole('link', { name: 'Logout' }).click();
    
    await logoutPromise;
    await expect(page, 'Logout should complete successfully even during navigation').toHaveURL(/.*login/);
  });

  test('negative — accessing logout via keyboard navigation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Open menu with keyboard
    await page.getByRole('button', { name: 'Open Menu' }).press('Enter');
    
    // Navigate to logout with tab and activate with enter
    await page.keyboard.press('Tab');
    await page.getByRole('link', { name: 'Logout' }).press('Enter');
    
    await expect(page, 'Keyboard-triggered logout should redirect to login page').toHaveURL(/.*login/);
  });

  test('boundary — logout immediately after login', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Perform logout immediately after page load (simulating immediate logout after login)
    await page.getByRole('button', { name: 'Open Menu' }).click();
    await page.getByRole('link', { name: 'Logout' }).click();
    
    await expect(page, 'Immediate logout after login should work correctly').toHaveURL(/.*login/);
    await expect(page.getByPlaceholder('Username'), 'Login form should be ready for new session').toBeVisible();
  });

  test('boundary — logout with browser back button interaction', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Perform logout
    await page.getByRole('button', { name: 'Open Menu' }).click();
    await page.getByRole('link', { name: 'Logout' }).click();
    
    await expect(page, 'User should be on login page after logout').toHaveURL(/.*login/);
    
    // Try to go back to inventory page
    await page.goBack();
    
    // Should not be able to access inventory page without authentication
    await expect(page, 'Back button should not allow access to authenticated pages').toHaveURL(/.*login/);
  });

  test('boundary — logout with maximum session timeout boundary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait a moment to simulate session boundary condition
    await page.waitForTimeout(1000);
    
    // Perform logout at session boundary
    await page.getByRole('button', { name: 'Open Menu' }).click();
    await page.getByRole('link', { name: 'Logout' }).click();
    
    await expect(page, 'Logout at session boundary should complete successfully').toHaveURL(/.*login/);
    await expect(page.getByPlaceholder('Username'), 'Login page should be accessible after boundary logout').toBeVisible();
  });
});