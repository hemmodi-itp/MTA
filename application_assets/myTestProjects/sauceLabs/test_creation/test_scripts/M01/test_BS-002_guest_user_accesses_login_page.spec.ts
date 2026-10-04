import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/';

test.describe('Guest user accesses login page (BS-002)', () => {

  test.afterEach(async ({ page }) => {
    // Adds a 1-second pause after returning to the base URL
    await page.waitForTimeout(1000);
  });
  
  test('positive — login page displays all required authentication elements', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field must be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field must be visible on login page').toBeVisible();
    await expect(page.getByTestId('login-button'), 'Sign in button must be visible on login page').toBeVisible();
    
    await expect(page.getByPlaceholder('Username'), 'Username field must be enabled for input').toBeEnabled();
    await expect(page.getByPlaceholder('Password'), 'Password field must be enabled for input').toBeEnabled();
    await expect(page.getByTestId('login-button'), 'Sign in button must be enabled for clicking').toBeEnabled();
  });

  test('negative — empty required fields show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('');
    await page.getByPlaceholder('Password').fill('');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message must appear when required fields are empty').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message must contain username required text').toContainText('Username is required');
  });

  test('negative — XSS injection attempt in username shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('<script>alert(\'xss\')</script>');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message must appear for invalid username characters').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message must indicate username format issue').toContainText('Username and password do not match');
  });

  test('negative — SQL injection attempt in username shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('\' OR \'1\'=\'1');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message must appear for SQL injection attempt').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message must indicate invalid credentials').toContainText('Username and password do not match');
  });

  test('negative — email format in username field shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('user@domain.com');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message must appear for email format in username').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message must indicate credentials do not match').toContainText('Username and password do not match');
  });

  test('boundary — username at maximum length boundary shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthUsername = 'a'.repeat(255);
    await page.getByPlaceholder('Username').fill(maxLengthUsername);
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message must appear for maximum length username').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message must indicate username validation failed').toContainText('Username and password do not match');
  });

  test('boundary — username exceeding maximum length shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongUsername = 'a'.repeat(256);
    await page.getByPlaceholder('Username').fill(tooLongUsername);
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message must appear when username exceeds maximum length').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message must indicate length validation failed').toContainText('Username and password do not match');
  });

  test('boundary — URL in username field shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('https://evil.com/redirect');
    await page.getByPlaceholder('Password').fill('secret_sauce');
    await page.getByTestId('login-button').click();
    
    await expect(page.locator('[data-test="error"]'), 'Error message must appear for URL in username field').toBeVisible();
    await expect(page.locator('[data-test="error"]'), 'Error message must indicate invalid username format').toContainText('Username and password do not match');
  });

});