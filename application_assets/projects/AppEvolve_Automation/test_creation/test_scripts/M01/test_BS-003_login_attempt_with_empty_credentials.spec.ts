import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/';

test.describe('Login Attempt with Empty Credentials (BS-003)', () => {
  test('positive — valid form submission succeeds', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username input field should be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password input field should be visible on login page').toBeVisible();
    
    await page.getByPlaceholder('Username').fill('john.doe@example.com');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.url(), 'Should navigate away from login page after successful authentication').not.toContain('/auth/');
  });

  test('negative — empty required fields show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByPlaceholder('Username'), 'Username input field should be visible').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password input field should be visible').toBeVisible();
    
    await page.getByPlaceholder('Username').fill('');
    await page.getByPlaceholder('Password').fill('');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.locator('.alert-error, .error-message, [role="alert"]'), 'Validation error message should appear for empty fields').toBeVisible();
    await expect(page.url(), 'Should remain on login page when validation fails').toContain('/auth/');
  });

  test('negative — XSS/HTML injection in username shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('<script>alert(\'xss\')</script>');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.locator('.alert-error, .error-message, [role="alert"]'), 'Error message should appear for invalid characters in username').toBeVisible();
    await expect(page.url(), 'Should remain on login page when username contains invalid characters').toContain('/auth/');
  });

  test('negative — SQL injection in username shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('\' OR \'1\'=\'1');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.locator('.alert-error, .error-message, [role="alert"]'), 'Error message should appear for SQL injection attempt in username').toBeVisible();
    await expect(page.url(), 'Should remain on login page when username contains SQL injection').toContain('/auth/');
  });

  test('negative — non-ASCII characters in username shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('あいうえお🔥🎉');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.locator('.alert-error, .error-message, [role="alert"]'), 'Error message should appear for unicode characters in username').toBeVisible();
    await expect(page.url(), 'Should remain on login page when username contains non-ASCII characters').toContain('/auth/');
  });

  test('boundary — username at maximum length shows authentication error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthUsername = 'a'.repeat(255);
    await page.getByPlaceholder('Username').fill(maxLengthUsername);
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.locator('.alert-error, .error-message, [role="alert"]'), 'Error message should appear for username at maximum length boundary').toBeVisible();
    await expect(page.url(), 'Should remain on login page when username is at max length').toContain('/auth/');
  });

  test('boundary — username exceeds maximum length shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongUsername = 'a'.repeat(256);
    await page.getByPlaceholder('Username').fill(tooLongUsername);
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.locator('.alert-error, .error-message, [role="alert"]'), 'Error message should appear when username exceeds maximum length').toBeVisible();
    await expect(page.url(), 'Should remain on login page when username is too long').toContain('/auth/');
  });

  test('boundary — URL as username shows authentication error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username').fill('https://evil.com/redirect');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.locator('.alert-error, .error-message, [role="alert"]'), 'Error message should appear when URL is used as username').toBeVisible();
    await expect(page.url(), 'Should remain on login page when username is a URL').toContain('/auth/');
  });
});