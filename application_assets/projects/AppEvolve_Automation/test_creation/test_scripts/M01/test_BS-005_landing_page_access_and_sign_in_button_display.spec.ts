import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/';

test.describe('Landing Page Access and Sign In Button Display (BS-005)', () => {
  test('positive — landing page loads with visible and clickable sign in button', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must be visible on landing page').toBeVisible();
    await expect(signInButton, 'Sign In button must be enabled and clickable').toBeEnabled();
  });

  test('negative — sign in button remains functional after page refresh with corrupted session', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate corrupted session data
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'invalid_token_###');
      sessionStorage.setItem('user_session', '<script>alert("xss")</script>');
    });
    
    await page.reload();
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must remain visible after corrupted session reload').toBeVisible();
    await expect(signInButton, 'Sign In button must remain clickable despite corrupted session').toBeEnabled();
  });

  test('negative — sign in button accessible with malformed URL parameters', async ({ page }) => {
    await page.goto(`${BASE_URL}?redirect=javascript:alert(1)&token='; DROP TABLE users; --`);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must be visible with malformed URL parameters').toBeVisible();
    await expect(signInButton, 'Sign In button must be clickable with malformed URL parameters').toBeEnabled();
  });

  test('negative — sign in button functions with empty cookie values', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set empty and special character cookies
    await page.context().addCookies([
      { name: 'session_id', value: '', url: BASE_URL },
      { name: 'auth_state', value: '""', url: BASE_URL },
      { name: 'user_pref', value: '{}', url: BASE_URL }
    ]);
    
    await page.reload();
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must be visible with empty cookie values').toBeVisible();
    await expect(signInButton, 'Sign In button must be clickable with empty cookie values').toBeEnabled();
  });

  test('negative — sign in button persists with special characters in browser storage', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Inject special characters into browser storage
    await page.evaluate(() => {
      localStorage.setItem('app_config', '!@#$%^&*()_+{}[]|\\:";\'<>?,./');
      sessionStorage.setItem('temp_data', '™£¢∞§¶•ªº–≠');
    });
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must remain visible with special characters in storage').toBeVisible();
    await expect(signInButton, 'Sign In button must remain clickable with special characters in storage').toBeEnabled();
  });

  test('boundary — sign in button accessible at minimum viewport dimensions', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(BASE_URL);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must be visible at minimum viewport width (320px)').toBeVisible();
    await expect(signInButton, 'Sign In button must be clickable at minimum viewport width').toBeEnabled();
  });

  test('boundary — sign in button functions with maximum URL length parameters', async ({ page }) => {
    const longParam = 'a'.repeat(2048);
    await page.goto(`${BASE_URL}?very_long_parameter=${longParam}&another_param=${longParam}`);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must be visible with maximum length URL parameters').toBeVisible();
    await expect(signInButton, 'Sign In button must be clickable with maximum length URL parameters').toBeEnabled();
  });

  test('boundary — sign in button remains functional with maximum browser storage usage', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Fill browser storage to near capacity
    const largeData = 'x'.repeat(1024 * 1024); // 1MB string
    await page.evaluate((data) => {
      try {
        for (let i = 0; i < 5; i++) {
          localStorage.setItem(`large_item_${i}`, data);
          sessionStorage.setItem(`session_item_${i}`, data);
        }
      } catch (e) {
        // Storage full, which is expected
      }
    }, largeData);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must be visible with maximum browser storage usage').toBeVisible();
    await expect(signInButton, 'Sign In button must be clickable with maximum browser storage usage').toBeEnabled();
  });
});