import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/';

test.describe('Login Attempt with Empty Password Only (BS-004)', () => {

  test('positive — valid username with empty password shows password validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill('john.doe@company.com');
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Password is required'), 'Password validation error must be displayed').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field must preserve entered value').toHaveValue('john.doe@company.com');
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

  test('negative — empty username and password shows both field validation errors', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill('');
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Username and password are required'), 'Both username and password validation error must be displayed').toBeVisible();
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

  test('negative — XSS payload in username with empty password shows password validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill('<script>alert(\'xss\')</script>');
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Password is required'), 'Password validation error must be displayed').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field must preserve XSS payload without execution').toHaveValue('<script>alert(\'xss\')</script>');
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

  test('negative — SQL injection in username with empty password shows password validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill('\' OR \'1\'=\'1');
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Password is required'), 'Password validation error must be displayed').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field must preserve SQL injection payload').toHaveValue('\' OR \'1\'=\'1');
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

  test('negative — unicode characters in username with empty password shows password validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill('あいうえお🔥🎉');
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Password is required'), 'Password validation error must be displayed').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field must preserve unicode characters').toHaveValue('あいうえお🔥🎉');
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

  test('boundary — username at maximum length with empty password shows password validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthUsername = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill(maxLengthUsername);
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Password is required'), 'Password validation error must be displayed').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field must preserve maximum length value').toHaveValue(maxLengthUsername);
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

  test('boundary — username exceeding maximum length with empty password shows password validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongUsername = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill(tooLongUsername);
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Password is required'), 'Password validation error must be displayed').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field must handle overly long input').toHaveValue(tooLongUsername);
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

  test('boundary — URL in username with empty password shows password validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByPlaceholder('Username', 'Username input field must be visible').fill('https://evil.com/redirect');
    await page.getByPlaceholder('Password', 'Password input field must be visible').fill('');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Password is required'), 'Password validation error must be displayed').toBeVisible();
    await expect(page.getByPlaceholder('Username'), 'Username field must preserve URL input without navigation').toHaveValue('https://evil.com/redirect');
    await expect(page.url(), 'User must remain on login page').toContain('/auth');
  });

});