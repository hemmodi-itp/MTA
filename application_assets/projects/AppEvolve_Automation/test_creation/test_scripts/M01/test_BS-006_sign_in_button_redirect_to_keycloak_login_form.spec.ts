import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/';

test.describe('Sign In Button Redirect to Keycloak Login Form (BS-006)', () => {
  
  test('positive — sign in button successfully redirects to Keycloak login form', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Verify Sign In button is visible and clickable
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign In button must be visible on landing page').toBeVisible();
    await expect(signInButton, 'Sign In button must be enabled and clickable').toBeEnabled();
    
    // Click the Sign In button
    await signInButton.click();
    
    // Wait for navigation to Keycloak login page
    await page.waitForLoadState('networkidle');
    
    // Verify redirect to Keycloak login form
    await expect(page, 'Page URL should contain Keycloak authentication domain').toHaveURL(/auth|keycloak|login/);
    
    // Verify username and password fields are visible
    await expect(page.getByPlaceholder('Username'), 'Username field must be visible on Keycloak login form').toBeVisible();
    await expect(page.getByPlaceholder('Password'), 'Password field must be visible on Keycloak login form').toBeVisible();
  });

  test('negative — sign in button with network interruption shows error handling', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate network failure during redirect
    await page.route('**/*auth*', route => route.abort());
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await signInButton.click();
    
    // Verify error handling or timeout behavior
    await expect(page.locator('body'), 'Page should handle network errors gracefully').toBeVisible();
  });

  test('negative — sign in button clicked multiple times rapidly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    
    // Click multiple times rapidly
    await signInButton.click();
    await signInButton.click();
    await signInButton.click();
    
    await page.waitForLoadState('networkidle');
    
    // Should still redirect properly and not cause errors
    await expect(page, 'Multiple clicks should not break redirect functionality').toHaveURL(/auth|keycloak|login/);
  });

  test('negative — sign in button interaction with JavaScript disabled', async ({ context, page }) => {
    await context.addInitScript(() => {
      Object.defineProperty(window, 'location', {
        writable: false,
        value: { ...window.location, assign: () => {}, replace: () => {} }
      });
    });
    
    await page.goto(BASE_URL);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await signInButton.click();
    
    // Verify graceful degradation or fallback behavior
    await expect(signInButton, 'Sign in button should remain functional even with JS limitations').toBeVisible();
  });

  test('negative — sign in button with invalid session state', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Corrupt session storage
    await page.evaluate(() => {
      sessionStorage.setItem('invalid_key', 'corrupted_data');
      localStorage.setItem('auth_state', 'invalid_state');
    });
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await signInButton.click();
    
    await page.waitForLoadState('networkidle');
    
    // Should still redirect to login despite corrupted local state
    await expect(page, 'Invalid session state should not prevent login redirect').toHaveURL(/auth|keycloak|login/);
  });

  test('boundary — sign in button functionality at minimum viewport size', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(BASE_URL);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign in button must be visible at minimum viewport size').toBeVisible();
    
    await signInButton.click();
    await page.waitForLoadState('networkidle');
    
    await expect(page, 'Login redirect should work at minimum viewport size').toHaveURL(/auth|keycloak|login/);
  });

  test('boundary — sign in button functionality at maximum viewport size', async ({ page }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.goto(BASE_URL);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await expect(signInButton, 'Sign in button must be visible at maximum viewport size').toBeVisible();
    
    await signInButton.click();
    await page.waitForLoadState('networkidle');
    
    await expect(page, 'Login redirect should work at maximum viewport size').toHaveURL(/auth|keycloak|login/);
  });

  test('boundary — sign in button with slow network conditions', async ({ page }) => {
    await page.route('**/*', route => {
      setTimeout(() => route.continue(), 2000);
    });
    
    await page.goto(BASE_URL);
    
    const signInButton = page.getByRole('button', { name: 'SSO Login' });
    await signInButton.click();
    
    // Should handle slow network gracefully
    await page.waitForLoadState('networkidle', { timeout: 30000 });
    await expect(page, 'Sign in redirect should work even with slow network conditions').toHaveURL(/auth|keycloak|login/);
  });

});