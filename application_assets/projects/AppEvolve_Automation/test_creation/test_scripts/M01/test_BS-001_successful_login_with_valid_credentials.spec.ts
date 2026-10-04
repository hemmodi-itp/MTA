import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/';

test.describe('Successful Login with Valid Credentials (BS-001)', () => {

  test('positive — valid credentials login redirects to dashboard', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    await page.getByPlaceholder('Username').fill('john.smith@company.com');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page, 'User should be redirected to dashboard after successful login').toHaveURL(/.*\/appevolve\/dashboard/);
    await expect(page.getByText('Dashboard'), 'Dashboard page content should be visible').toBeVisible();
  });

  test('negative — empty username and password show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    await page.getByPlaceholder('Username').fill('');
    await page.getByPlaceholder('Password').fill('');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText(/required/i), 'Required field validation error should be displayed').toBeVisible();
    await expect(page, 'User should remain on login page after validation error').toHaveURL(/.*\/auth\/.*/);
  });

  test('negative — XSS script in username field shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    await page.getByPlaceholder('Username').fill('<script>alert(\'xss\')</script>');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText(/invalid/i), 'Invalid username format error should be displayed').toBeVisible();
    await expect(page, 'User should remain on login page after invalid input').toHaveURL(/.*\/auth\/.*/);
  });

  test('negative — SQL injection in username field shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    await page.getByPlaceholder('Username').fill('\' OR \'1\'=\'1');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText(/invalid/i), 'Invalid username format error should be displayed for SQL injection attempt').toBeVisible();
    await expect(page, 'User should remain on login page after SQL injection attempt').toHaveURL(/.*\/auth\/.*/);
  });

  test('negative — incorrect credentials show authentication error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    await page.getByPlaceholder('Username').fill('nonexistent.user@company.com');
    await page.getByPlaceholder('Password').fill('WrongPassword123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText(/invalid.*username.*password/i), 'Invalid credentials error message should be displayed').toBeVisible();
    await expect(page, 'User should remain on login page after failed authentication').toHaveURL(/.*\/auth\/.*/);
  });

  test('boundary — username at maximum length is processed', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    const maxLengthUsername = 'a'.repeat(255);
    await page.getByPlaceholder('Username').fill(maxLengthUsername);
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    // Should either succeed (if valid) or show appropriate validation
    const usernameField = page.getByPlaceholder('Username');
    await expect(usernameField, 'Username field should accept maximum length input').toHaveValue(maxLengthUsername);
  });

  test('boundary — username exceeding maximum length shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    const tooLongUsername = 'a'.repeat(256);
    await page.getByPlaceholder('Username').fill(tooLongUsername);
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText(/255.*characters/i), 'Username length validation error should be displayed').toBeVisible();
    await expect(page, 'User should remain on login page after length validation error').toHaveURL(/.*\/auth\/.*/);
  });

  test('boundary — URL input in username field shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'SSO Login' }).click();
    
    // Wait for Keycloak login page to load
    await page.waitForURL('**/auth/**', { timeout: 10000 });
    
    await page.getByPlaceholder('Username').fill('https://evil.com/redirect');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText(/invalid.*format/i), 'Invalid username format error should be displayed for URL input').toBeVisible();
    await expect(page, 'User should remain on login page after invalid URL input').toHaveURL(/.*\/auth\/.*/);
  });

});