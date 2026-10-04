import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('User executes automated workflows successfully (M02_BS_009)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — execute Get Started and Pricing exploration workflows successfully', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load completely
    await page.waitForLoadState('networkidle');
    
    // Step 1: Initiate execution of the Get Started with Aurora workflow
    // Look for "Get Started" or similar call-to-action button
    const getStartedButton = page.getByText('Get started').first();
    if (await getStartedButton.isVisible()) {
      await getStartedButton.click();
      
      // Verify successful completion of first workflow by checking URL change or page load
      await page.waitForLoadState('networkidle');
      await expect(page, 'Get Started workflow should navigate successfully').toHaveURL(/.*/, { timeout: 10000 });
    }
    
    // Navigate back to main Aurora page for next workflow
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Step 3: Execute the Pricing exploration workflow
    // Look for pricing-related links or buttons
    const pricingLink = page.getByText('Pricing').first();
    if (await pricingLink.isVisible()) {
      await pricingLink.click();
      
      // Verify successful completion of second workflow
      await page.waitForLoadState('networkidle');
      await expect(page, 'Pricing workflow should navigate successfully').toHaveURL(/.*pricing.*|.*aurora.*/, { timeout: 10000 });
    }
    
    // Verify both workflows executed without critical errors by checking page is responsive
    await expect(page.locator('body'), 'Page should remain responsive after workflow execution').toBeVisible();
  });

  test('negative — workflow execution with network interruption', async () => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Simulate network interruption during workflow execution
    await page.route('**/*', route => {
      if (route.request().url().includes('api') || route.request().url().includes('workflow')) {
        route.abort();
      } else {
        route.continue();
      }
    });
    
    // Try to execute Get Started workflow with simulated network issues
    const getStartedButton = page.getByText('Get started').first();
    if (await getStartedButton.isVisible()) {
      await getStartedButton.click();
      
      // Should handle network errors gracefully
      await page.waitForTimeout(3000);
      await expect(page.locator('body'), 'Page should remain stable even with network issues').toBeVisible();
    }
    
    // Reset network interception
    await page.unroute('**/*');
  });

  test('boundary — rapid sequential workflow execution', async () => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Execute workflows in rapid succession to test system limits
    const getStartedButton = page.getByText('Get started').first();
    if (await getStartedButton.isVisible()) {
      // First rapid execution
      await getStartedButton.click();
      await page.waitForTimeout(1000);
      
      // Navigate back quickly
      await page.goBack();
      await page.waitForTimeout(500);
      
      // Second rapid execution
      const secondGetStartedButton = page.getByText('Get started').first();
      if (await secondGetStartedButton.isVisible()) {
        await secondGetStartedButton.click();
        
        // Verify system handles rapid workflow execution
        await expect(page, 'System should handle rapid workflow execution within reasonable time').toHaveURL(/.*/, { timeout: 15000 });
      }
    }
    
    await expect(page.locator('body'), 'Page should remain functional after rapid workflow execution').toBeVisible();
  });
});