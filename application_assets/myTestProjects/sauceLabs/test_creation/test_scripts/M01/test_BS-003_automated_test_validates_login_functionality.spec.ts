import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/';

test.describe('Automated test validates login functionality (BS-003)', () => {
  
  test.afterEach(async ({ page }) => {
    // Adds a 1-second pause after returning to the base URL
    await page.waitForTimeout(1000);
  });
  
  test('positive — valid login with standard_user credentials succeeds', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Validate presence of username field
    await expect(page.getByPlaceholder('Username'), 'Username field must be visible on login page').toBeVisible();
    
    // Validate presence of password field
    await expect(page.getByPlaceholder('Password'), 'Password field must be visible on login page').toBeVisible();
    
    // Validate presence of signin button
    await expect(page.getByTestId('login-button'), 'Login button must be visible on login page').toBeVisible();
    
    // Execute login test with standard_user credentials
    await page.getByPlaceholder('Username').fill('standard_user');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    // Verify successful login by checking for inventory page
    await expect(page, 'User should be redirected to inventory page after successful login').toHaveURL(/.*inventory.html/);
  });

  test('negative — empty required fields show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt login with empty fields
    await page.getByPlaceholder('Username').fill('');
    await page.getByPlaceholder('Password').fill('');
    await page.getByTestId('login-button').click();
    
    // Check for error message
    await expect(page.locator('[data-test="error"]'), 'Error message should appear when required fields are empty').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message should indicate username is required').toContainText('Username is required');
  });

  test('negative — XSS injection attempt shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt login with XSS payload
    await page.getByPlaceholder('Username').fill('<script>alert(\'xss\')</script>');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    // Check that login fails and user remains on login page
    await expect(page.locator('[data-test="error"]'), 'Error message should appear for invalid username characters').toBeVisible();
    await expect(page, 'User should remain on login page when XSS attempt fails').toHaveURL(BASE_URL);
  });

  test('negative — SQL injection attempt shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt login with SQL injection payload
    await page.getByPlaceholder('Username').fill('\' OR \'1\'=\'1');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    // Check that login fails and user remains on login page
    await expect(page.locator('[data-test="error"]'), 'Error message should appear for SQL injection attempt').toBeVisible();
    await expect(page, 'User should remain on login page when SQL injection fails').toHaveURL(BASE_URL);
  });

  test('negative — whitespace only fields show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt login with whitespace only
    await page.getByPlaceholder('Username').fill('   ');
    await page.getByPlaceholder('Password').fill('\t\t');
    await page.getByTestId('login-button').click();
    
    // Check for error message
    await expect(page.locator('[data-test="error"]'), 'Error message should appear when fields contain only whitespace').toBeVisible();
    await expect(page, 'User should remain on login page when whitespace validation fails').toHaveURL(BASE_URL);
  });

  test('boundary — username at maximum length boundary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Test with username at boundary length
    const boundaryUsername = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    
    await page.getByPlaceholder('Username').fill(boundaryUsername);
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    // Should handle boundary case gracefully
    await expect(page.locator('[data-test="error"]'), 'Error message should appear for username at boundary length').toBeVisible();
    await expect(page, 'User should remain on login page when boundary validation fails').toHaveURL(BASE_URL);
  });

  test('boundary — username exceeds maximum length', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Test with username exceeding maximum length
    const tooLongUsername = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    
    await page.getByPlaceholder('Username').fill(tooLongUsername);
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    // Should reject overly long username
    await expect(page.locator('[data-test="error"]'), 'Error message should appear when username exceeds maximum length').toBeVisible();
    await expect(page, 'User should remain on login page when length validation fails').toHaveURL(BASE_URL);
  });

  test('boundary — URL input in username field', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Test with URL in username field
    await page.getByPlaceholder('Username').fill('https://evil.com/redirect');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    // Should reject URL format in username
    await expect(page.locator('[data-test="error"]'), 'Error message should appear when username contains URL format').toBeVisible();
    await expect(page, 'User should remain on login page when URL validation fails').toHaveURL(BASE_URL);
  });

});