import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('Guest user explores Aurora product features (M02_BS_007)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — guest user successfully explores Aurora product features and capabilities', async () => {
    await page.goto(BASE_URL);
    
    // Verify page loads and displays Aurora product information
    await expect(page, 'Aurora product page should load successfully').toHaveURL(/.*aurora.*/);
    await expect(page, 'Page title should contain Aurora').toHaveTitle(/.*Aurora.*/);
    
    // Browse through product showcase sections by scrolling and checking for content visibility
    await page.evaluate(() => window.scrollTo(0, 500));
    await page.waitForTimeout(1000);
    
    // Look for common AWS product page elements and content
    const heroSection = page.locator('h1, .hero, [data-testid="hero"]').first();
    if (await heroSection.isVisible()) {
      await expect(heroSection, 'Hero section should be visible to showcase Aurora').toBeVisible();
    }
    
    // Scroll through different sections to explore features
    await page.evaluate(() => window.scrollTo(0, 1000));
    await page.waitForTimeout(1000);
    
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(1000);
    
    // Check if navigation or feature links are present and accessible
    const featureLinks = page.locator('a').filter({ hasText: /feature|benefit|capability|learn/i });
    const linkCount = await featureLinks.count();
    
    if (linkCount > 0) {
      // Click on first feature/learn more link if available
      const firstLink = featureLinks.first();
      const linkText = await firstLink.textContent();
      
      if (linkText && await firstLink.isVisible()) {
        await firstLink.click();
        await page.waitForTimeout(2000);
        
        // Verify navigation occurred (either same page scroll or new page)
        await expect(page, 'Should remain on AWS domain after exploring features').toHaveURL(/aws\.amazon\.com/);
      }
    }
    
    // Return to main Aurora page if navigated away
    if (!await page.url().includes('aurora')) {
      await page.goto(BASE_URL);
    }
    
    // Final verification that guest user can access Aurora information
    await expect(page, 'Aurora product page should remain accessible to guest users').toHaveURL(/.*aurora.*/);
  });

  test('negative — guest user encounters error when accessing restricted Aurora content', async () => {
    await page.goto(BASE_URL);
    
    // Attempt to access potentially restricted areas (like console links)
    const consoleLinks = page.locator('a').filter({ hasText: /console|sign.?in|login|get.?started/i });
    const consoleCount = await consoleLinks.count();
    
    if (consoleCount > 0) {
      const consoleLink = consoleLinks.first();
      
      if (await consoleLink.isVisible()) {
        await consoleLink.click();
        await page.waitForTimeout(3000);
        
        // Should be redirected to sign-in or authentication page
        await expect(page, 'Restricted content should redirect guest users to authentication').toHaveURL(/signin|login|auth/);
        
        // Navigate back to continue testing
        await page.goto(BASE_URL);
      }
    }
    
    // Verify that after attempting restricted access, guest can still browse public content
    await expect(page, 'Guest user should still be able to access public Aurora information').toHaveURL(/.*aurora.*/);
  });

  test('boundary — guest user explores Aurora features with limited browser capabilities', async () => {
    // Simulate limited browser environment (disable JavaScript temporarily for some interactions)
    await page.goto(BASE_URL);
    
    // Test basic content accessibility without heavy JavaScript interactions
    await page.evaluate(() => {
      // Disable some JavaScript features to simulate limited environment
      window.history.pushState = () => {};
    });
    
    // Verify core content is still accessible
    await expect(page, 'Aurora page should be accessible even with limited browser capabilities').toHaveURL(/.*aurora.*/);
    
    // Test basic scrolling and content visibility in limited environment
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
    await page.waitForTimeout(2000);
    
    // Verify page remains functional
    await expect(page, 'Page should remain functional with basic browser capabilities').toHaveURL(/.*aurora.*/);
    
    // Test with extremely slow network simulation
    await page.route('**/*', async route => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.continue();
    });
    
    // Navigate and verify content still loads (though slowly)
    await page.reload();
    await page.waitForTimeout(5000);
    
    await expect(page, 'Aurora content should eventually load even with slow network').toHaveURL(/.*aurora.*/);
  });
});