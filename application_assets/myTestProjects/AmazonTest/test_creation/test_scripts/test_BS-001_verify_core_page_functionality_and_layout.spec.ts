import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Verify Core Page Functionality and Layout (BS-001)', () => {
  
  test('positive — deals page loads successfully with proper branding and layout', async ({ page }) => {
    // Navigate to the deals page
    const response = await page.goto(BASE_URL);
    
    // Verify the page returns HTTP 200 status code
    await expect(response?.status(), 'Deals page should return HTTP 200 status code').toBe(200);
    
    // Check that core layout regions paint without console faults
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    
    // Wait for page to load completely
    await page.waitForLoadState('networkidle');
    
    // Verify no console errors occurred
    await expect(consoleErrors.length, 'Page should load without console errors').toBe(0);
    
    // Confirm page title contains appropriate localized branding strings
    const pageTitle = await page.title();
    await expect(pageTitle.toLowerCase().includes('deals') || pageTitle.toLowerCase().includes('amazon'), 'Page title should contain deals or Amazon branding').toBeTruthy();
    
    // Verify branding indicator for localized content
    await expect(page.getByRole('link', { name: '.in' }), 'Localized branding indicator (.in) should be visible').toBeVisible();
    
    // Verify main deals page navigation link
    await expect(page.getByRole('link', { name: 'Today\'s Deals' }), 'Today\'s Deals navigation link should be visible').toBeVisible();
  });

  test('negative — page handles invalid URL parameters gracefully', async ({ page }) => {
    const invalidUrl = BASE_URL + '&invalid=<script>alert("xss")</script>';
    const response = await page.goto(invalidUrl);
    
    await expect(response?.status(), 'Page should handle invalid parameters and still return success status').toBeLessThan(500);
    await expect(page.getByRole('link', { name: '.in' }), 'Page branding should still be visible with invalid parameters').toBeVisible();
  });

  test('negative — page loads correctly with special characters in URL', async ({ page }) => {
    const specialCharUrl = BASE_URL + '&test=%20%21%40%23%24%25%5E%26%2A';
    const response = await page.goto(specialCharUrl);
    
    await expect(response?.status(), 'Page should handle special characters in URL parameters').toBeLessThan(500);
    await expect(page.getByRole('link', { name: 'Today\'s Deals' }), 'Deals navigation should remain functional with special characters').toBeVisible();
  });

  test('negative — page handles SQL injection attempts in URL parameters', async ({ page }) => {
    const sqlInjectionUrl = BASE_URL + '&search=\'; DROP TABLE users; --';
    const response = await page.goto(sqlInjectionUrl);
    
    await expect(response?.status(), 'Page should safely handle SQL injection attempts').toBeLessThan(500);
    await expect(page.getByRole('link', { name: '.in' }), 'Localized branding should remain intact after SQL injection attempt').toBeVisible();
  });

  test('negative — page responds appropriately to malformed parameters', async ({ page }) => {
    const malformedUrl = BASE_URL + '&ref==invalid&&test=';
    const response = await page.goto(malformedUrl);
    
    await expect(response?.status(), 'Page should handle malformed URL parameters gracefully').toBeLessThan(500);
    await expect(page.getByRole('link', { name: 'Today\'s Deals' }), 'Core functionality should work despite malformed parameters').toBeVisible();
  });

  test('boundary — page loads with maximum length URL parameters', async ({ page }) => {
    const longParam = 'a'.repeat(255);
    const longUrl = BASE_URL + `&test=${longParam}`;
    const response = await page.goto(longUrl);
    
    await expect(response?.status(), 'Page should handle maximum length URL parameters').toBeLessThan(500);
    await expect(page.getByRole('link', { name: '.in' }), 'Branding should display correctly with long URL parameters').toBeVisible();
    
    const pageTitle = await page.title();
    await expect(pageTitle.length, 'Page title should have reasonable length even with long URL params').toBeGreaterThan(0);
  });

  test('boundary — page handles empty parameter values correctly', async ({ page }) => {
    const emptyParamUrl = BASE_URL + '&ref=&test=&empty=';
    const response = await page.goto(emptyParamUrl);
    
    await expect(response?.status(), 'Page should handle empty parameter values without errors').toBeLessThan(500);
    await expect(page.getByRole('link', { name: 'Today\'s Deals' }), 'Navigation should work with empty URL parameters').toBeVisible();
  });

  test('boundary — page responds to URL with excessive parameters', async ({ page }) => {
    let excessiveUrl = BASE_URL;
    for (let i = 0; i < 50; i++) {
      excessiveUrl += `&param${i}=value${i}`;
    }
    const response = await page.goto(excessiveUrl);
    
    await expect(response?.status(), 'Page should handle excessive number of URL parameters').toBeLessThan(500);
    await expect(page.getByRole('link', { name: '.in' }), 'Core branding should remain functional with many URL parameters').toBeVisible();
    
    // Verify page loads within reasonable time
    await page.waitForLoadState('domcontentloaded', { timeout: 10000 });
    await expect(page.getByRole('link', { name: 'Today\'s Deals' }), 'Page should fully load even with excessive parameters').toBeVisible();
  });
});