import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Investor Portal Access and Dashboard View (BS-003)', () => {
  
  test('positive — investor successfully accesses portal and views complete dashboard within 3 seconds', async ({ page }) => {
    const startTime = Date.now();
    
    await page.goto(BASE_URL);
    
    // Access secure login page
    await expect(page.getByRole('button', { name: 'Login' }), 'Login button must be visible on landing page').toBeVisible();
    await page.getByRole('button', { name: 'Login' }).click();
    
    // Complete authentication process
    await expect(page.getByPlaceholder('Email'), 'Email input must be visible on login page').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password input must be visible on login page').toBeVisible();
    
    await page.getByPlaceholder('Email').fill('investor@example.com');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    // Multi-factor authentication
    await expect(page.getByPlaceholder('Enter verification code'), 'MFA code input must be visible after login').toBeVisible();
    await page.getByPlaceholder('Enter verification code').fill('123456');
    await page.getByRole('button', { name: 'Verify' }).click();
    
    // View investor dashboard with investment overview
    await expect(page.getByText('Investment Dashboard'), 'Investment Dashboard heading must be visible').toBeVisible();
    await expect(page.getByText('Investment Overview'), 'Investment Overview section must be visible').toBeVisible();
    
    // Display current investment positions
    await expect(page.getByText('Current Positions'), 'Current Positions section must be displayed').toBeVisible();
    await expect(page.locator('[data-testid="positions-table"]'), 'Positions table must be present on dashboard').toBeVisible();
    
    // Display capital balances and commitments
    await expect(page.getByText('Capital Balances'), 'Capital Balances section must be displayed').toBeVisible();
    await expect(page.getByText('Commitments'), 'Commitments section must be displayed').toBeVisible();
    await expect(page.locator('[data-testid="balance-amount"]'), 'Balance amount must be displayed').toBeVisible();
    
    // Display recent distributions and transaction history
    await expect(page.getByText('Recent Distributions'), 'Recent Distributions section must be displayed').toBeVisible();
    await expect(page.getByText('Transaction History'), 'Transaction History section must be displayed').toBeVisible();
    await expect(page.locator('[data-testid="transactions-list"]'), 'Transactions list must be present').toBeVisible();
    
    const endTime = Date.now();
    const loadTime = endTime - startTime;
    expect(loadTime, 'Dashboard must load within 3 seconds').toBeLessThan(3000);
  });

  test('negative — empty login credentials show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Login' }).click();
    
    // Submit empty form
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Email is required'), 'Email required error must be displayed for empty email').toBeVisible();
    await expect(page.getByText('Password is required'), 'Password required error must be displayed for empty password').toBeVisible();
    await expect(page.url(), 'User must remain on login page after validation error').toContain('login');
  });

  test('negative — invalid characters in email show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Login' }).click();
    
    // Enter special characters in email
    await page.getByPlaceholder('Email').fill('invalid@#$%email');
    await page.getByPlaceholder('Password').fill('ValidPass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Please enter a valid email address'), 'Invalid email format error must be displayed').toBeVisible();
    await expect(page.url(), 'User must remain on login page after email validation error').toContain('login');
  });

  test('negative — SQL injection attempt in login fields fails securely', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Login' }).click();
    
    // Attempt SQL injection
    await page.getByPlaceholder('Email').fill("admin@example.com'; DROP TABLE users; --");
    await page.getByPlaceholder('Password').fill("' OR '1'='1");
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Invalid credentials'), 'Invalid credentials error must be shown for SQL injection attempt').toBeVisible();
    await expect(page.url(), 'User must remain on login page after failed injection attempt').toContain('login');
  });

  test('negative — wrong MFA code format shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Login' }).click();
    
    await page.getByPlaceholder('Email').fill('investor@example.com');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    // Enter wrong format MFA code
    await page.getByPlaceholder('Enter verification code').fill('abc123');
    await page.getByRole('button', { name: 'Verify' }).click();
    
    await expect(page.getByText('Verification code must be 6 digits'), 'MFA format error must be displayed for invalid format').toBeVisible();
    await expect(page.url(), 'User must remain on MFA page after validation error').toContain('verify');
  });

  test('boundary — maximum length email (254 chars) is accepted', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Login' }).click();
    
    // Create 254 character email (at boundary)
    const longEmail = 'a'.repeat(243) + '@example.com'; // 254 chars total
    
    await page.getByPlaceholder('Email').fill(longEmail);
    await page.getByPlaceholder('Password').fill('ValidPass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Invalid credentials'), 'System must handle boundary length email without format error').toBeVisible();
    expect(page.getByPlaceholder('Email'), 'Email field must retain the boundary length value').toHaveValue(longEmail);
  });

  test('boundary — email exceeding maximum length (255+ chars) shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Login' }).click();
    
    // Create 260 character email (exceeds boundary)
    const tooLongEmail = 'a'.repeat(249) + '@example.com'; // 260 chars total
    
    await page.getByPlaceholder('Email').fill(tooLongEmail);
    await page.getByPlaceholder('Password').fill('ValidPass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await expect(page.getByText('Email address is too long'), 'Email length validation error must be displayed').toBeVisible();
    await expect(page.url(), 'User must remain on login page after length validation error').toContain('login');
  });

  test('boundary — URL manipulation in redirect parameter is handled securely', async ({ page }) => {
    // Test URL input boundary with redirect parameter
    await page.goto(`${BASE_URL}?redirect=http://malicious-site.com/steal-data`);
    
    await page.getByRole('button', { name: 'Login' }).click();
    
    await page.getByPlaceholder('Email').fill('investor@example.com');
    await page.getByPlaceholder('Password').fill('SecurePass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();
    
    await page.getByPlaceholder('Enter verification code').fill('123456');
    await page.getByRole('button', { name: 'Verify' }).click();
    
    // After successful login, should redirect to internal dashboard, not external URL
    await expect(page.url(), 'System must redirect to internal dashboard, not external malicious URL').toContain(BASE_URL);
    await expect(page.url(), 'System must not redirect to external malicious site').not.toContain('malicious-site.com');
  });

});