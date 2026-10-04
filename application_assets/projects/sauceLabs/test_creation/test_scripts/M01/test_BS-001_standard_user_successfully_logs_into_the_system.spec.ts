import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/';

test.describe('Standard user successfully logs into the system (BS-001)', () => {
  test.afterEach(async ({ page }) => {
    // Adds a 1-second pause after returning to the base URL
    await page.waitForTimeout(1000);
  });

  test('positive — valid standard user login succeeds and redirects to dashboard', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username input field must be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password input field must be visible on login page').toBeVisible();
    await expect(page.getByTestId('login-button'), 'Login button must be visible on login page').toBeVisible();
    
    await page.getByPlaceholder('Username').fill('standard_user');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page, 'User should be redirected to inventory page after successful login').toHaveURL(/.*inventory\.html/);
    await expect(page.locator('.app_logo'), 'Swag Labs logo should be visible on dashboard').toBeVisible();
    await expect(page.locator('.inventory_list'), 'Product inventory list should be displayed on dashboard').toBeVisible();
    await page.waitForTimeout(1000); 
  });

  test('negative — empty username and password fields show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message should be displayed for empty credentials').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error should specify username is required').toContainText('Username is required');
    await expect(page, 'User should remain on login page after failed login attempt').toHaveURL(BASE_URL);
    await page.waitForTimeout(1000); 
  });

  test('negative — special characters in username field shows authentication error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('!@#$%^&*()');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message should be displayed for invalid username with special characters').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error should indicate authentication failure').toContainText('Username and password do not match');
    await expect(page, 'User should remain on login page after authentication failure').toHaveURL(BASE_URL);
  });

  test('negative — SQL injection attempt in password field shows authentication error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('standard_user');
    await page.getByPlaceholder('Password').fill("' OR '1'='1");
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message should be displayed for SQL injection attempt').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error should indicate authentication failure for malicious input').toContainText('Username and password do not match');
    await expect(page, 'User should remain on login page after SQL injection attempt').toHaveURL(BASE_URL);
  });

  test('negative — wrong password format shows authentication error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('standard_user');
    await page.getByPlaceholder('Password').fill('wrongpassword123');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message should be displayed for incorrect password').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error should indicate credentials do not match').toContainText('Username and password do not match');
    await expect(page, 'User should remain on login page after wrong password attempt').toHaveURL(BASE_URL);
  });

  test('boundary — username at maximum length boundary is processed', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthUsername = 'a'.repeat(255);
    await page.getByPlaceholder('Username').fill(maxLengthUsername);
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message should be displayed for boundary length username').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field should retain the entered boundary value').toHaveValue(maxLengthUsername);
    await expect(page, 'User should remain on login page after boundary test').toHaveURL(BASE_URL);
  });

  test('boundary — password exceeding maximum length is truncated or rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongPassword = 'a'.repeat(1000);
    await page.getByPlaceholder('Username').fill('standard_user');
    await page.getByPlaceholder('Password').fill(tooLongPassword);
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message should be displayed for excessively long password').toBeVisible();
    await expect(page, 'User should remain on login page after too long password test').toHaveURL(BASE_URL);
  });

  test('boundary — URL-like input in username field is handled appropriately', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const urlInput = 'https://malicious-site.com/redirect';
    await page.getByPlaceholder('Username').fill(urlInput);
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message should be displayed for URL input in username').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field should contain the URL input without causing redirect').toHaveValue(urlInput);
    await expect(page, 'User should remain on login page and not be redirected to malicious URL').toHaveURL(BASE_URL);
  });

});