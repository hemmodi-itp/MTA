import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/';

test.describe('Login Attempt with Invalid Password (BS-002)', () => {

  test('positive — valid username with invalid password shows authentication error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    await page.fill('[name="username"]', 'john.doe@company.com');
    await page.fill('[name="password"]', 'WrongPassword123!');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Invalid username or password'), 'Error message should be displayed for invalid credentials').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should still be present after failed login').toBeVisible();
    await expect(page.locator('[name="password"]'), 'Password field should still be present after failed login').toBeVisible();
  });

  test('negative — empty username and password fields show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    await page.fill('[name="username"]', '');
    await page.fill('[name="password"]', '');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Username and password are required'), 'Validation error should be shown for empty fields').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should remain visible after validation error').toBeVisible();
  });

  test('negative — XSS script injection in username field is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    await page.fill('[name="username"]', '<script>alert(\'xss\')</script>');
    await page.fill('[name="password"]', 'WrongPassword123!');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Invalid username format'), 'XSS injection should be rejected with format error').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should remain on page after XSS attempt').toBeVisible();
  });

  test('negative — SQL injection in username field is blocked', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    await page.fill('[name="username"]', '\' OR \'1\'=\'1');
    await page.fill('[name="password"]', 'WrongPassword123!');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Invalid username format'), 'SQL injection should be blocked with format error').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should still be present after SQL injection attempt').toBeVisible();
  });

  test('negative — malformed email format in username shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    await page.fill('[name="username"]', 'user@domain@com');
    await page.fill('[name="password"]', 'WrongPassword123!');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Invalid username or password'), 'Malformed email should show invalid credentials error').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should remain visible after format error').toBeVisible();
  });

  test('boundary — username at maximum allowed length is handled properly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    const maxLengthUsername = 'a'.repeat(255);
    await page.fill('[name="username"]', maxLengthUsername);
    await page.fill('[name="password"]', 'WrongPassword123!');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Invalid username or password'), 'Maximum length username should show credentials error').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should remain after boundary test').toBeVisible();
  });

  test('boundary — username exceeding maximum length shows length error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    const tooLongUsername = 'a'.repeat(300);
    await page.fill('[name="username"]', tooLongUsername);
    await page.fill('[name="password"]', 'WrongPassword123!');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Username is too long'), 'Excessively long username should show length error').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should remain visible after length validation').toBeVisible();
  });

  test('boundary — URL input in username field is rejected as invalid format', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field should be visible on login page').toBeVisible();
    
    await page.fill('[name="username"]', 'https://evil.com/redirect');
    await page.fill('[name="password"]', 'WrongPassword123!');
    
    await page.click('button[type="submit"]');
    
    await expect(page.getByText('Invalid username format'), 'URL in username should be rejected with format error').toBeVisible();
    await expect(page.locator('[name="username"]'), 'Username field should remain present after URL rejection').toBeVisible();
  });

});