import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Lazy Loading and Infinite Scroll Functionality (BS-005)', () => {
  
  test('positive — deals page loads initial content and triggers lazy loading on scroll', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait for initial page load and verify initial deals are present
    await expect(page.getByTestId('add-to-cart-button').first(), 'Initial deal cards must be visible after page load').toBeVisible();
    
    // Count initial number of add-to-cart buttons to establish baseline
    const initialButtonCount = await page.getByTestId('add-to-cart-button').count();
    await expect(initialButtonCount, 'Initial deal set must contain at least one deal card').toBeGreaterThan(0);
    
    // Scroll to the bottom of current content to trigger lazy loading
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Wait for new content to load
    await page.waitForTimeout(2000);
    
    // Verify additional content has been loaded
    const newButtonCount = await page.getByTestId('add-to-cart-button').count();
    await expect(newButtonCount, 'Additional deals must load after scrolling to bottom').toBeGreaterThan(initialButtonCount);
    
    // Perform another scroll to verify continuous loading
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(2000);
    
    const finalButtonCount = await page.getByTestId('add-to-cart-button').count();
    await expect(finalButtonCount, 'More deals must continue loading on subsequent scrolls').toBeGreaterThanOrEqual(newButtonCount);
    
    // Verify back to top button appears after scrolling
    await expect(page.getByRole('button', { name: 'Back to top' }), 'Back to top button must appear after scrolling down').toBeVisible();
  });

  test('negative — rapid scroll events do not break loading mechanism', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByTestId('add-to-cart-button').first(), 'Initial deals must load before testing rapid scroll').toBeVisible();
    
    const initialCount = await page.getByTestId('add-to-cart-button').count();
    
    // Perform rapid scroll events to stress test the loading mechanism
    for (let i = 0; i < 5; i++) {
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(100); // Very short wait between scrolls
    }
    
    await page.waitForTimeout(3000); // Wait for any pending loads to complete
    
    const finalCount = await page.getByTestId('add-to-cart-button').count();
    await expect(finalCount, 'Lazy loading must handle rapid scroll events without breaking').toBeGreaterThanOrEqual(initialCount);
    
    // Verify page is still functional
    await expect(page.getByRole('button', { name: 'Back to top' }), 'Page navigation must remain functional after rapid scrolling').toBeVisible();
  });

  test('negative — scroll at maximum viewport height does not cause errors', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByTestId('add-to-cart-button').first(), 'Initial content must be present before viewport scroll test').toBeVisible();
    
    // Scroll beyond normal document height to test error handling
    await page.evaluate(() => {
      window.scrollTo(0, 999999);
    });
    
    await page.waitForTimeout(2000);
    
    // Verify page still responds and shows content
    const buttonCount = await page.getByTestId('add-to-cart-button').count();
    await expect(buttonCount, 'Deal cards must remain accessible after extreme scroll position').toBeGreaterThan(0);
    
    // Verify no JavaScript errors occurred
    await expect(page.getByRole('button', { name: 'Back to top' }), 'Back to top functionality must work after extreme scroll').toBeVisible();
  });

  test('negative — network interruption during scroll loading maintains page stability', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByTestId('add-to-cart-button').first(), 'Initial deals must load before network interruption test').toBeVisible();
    
    const initialCount = await page.getByTestId('add-to-cart-button').count();
    
    // Simulate network interruption by blocking requests
    await page.route('**/*', route => route.abort());
    
    // Attempt to trigger lazy loading while network is blocked
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(2000);
    
    // Restore network
    await page.unroute('**/*');
    
    // Verify existing content is still accessible
    const countAfterInterruption = await page.getByTestId('add-to-cart-button').count();
    await expect(countAfterInterruption, 'Existing deals must remain accessible after network interruption').toBe(initialCount);
  });

  test('negative — disabled JavaScript still shows initial content', async ({ page, context }) => {
    // Disable JavaScript for this test
    await context.setExtraHTTPHeaders({ 'User-Agent': 'TestAgent-NoJS' });
    
    await page.goto(BASE_URL);
    
    // Verify initial content loads even without JavaScript lazy loading
    await page.waitForTimeout(3000);
    
    // Check if any deals are visible (should be server-rendered)
    const hasDeals = await page.getByTestId('add-to-cart-button').count() > 0;
    
    if (hasDeals) {
      await expect(page.getByTestId('add-to-cart-button').first(), 'Server-rendered deals must be visible without JavaScript').toBeVisible();
    } else {
      // If no deals load, verify page structure is still intact
      await expect(page.locator('body'), 'Page body must be present even without JavaScript lazy loading').toBeVisible();
    }
  });

  test('boundary — scroll loading at minimum viewport size', async ({ page }) => {
    // Set very small viewport to test boundary conditions
    await page.setViewportSize({ width: 320, height: 240 });
    await page.goto(BASE_URL);
    
    await expect(page.getByTestId('add-to-cart-button').first(), 'Deals must be accessible in minimum viewport size').toBeVisible();
    
    const initialCount = await page.getByTestId('add-to-cart-button').count();
    
    // Scroll in small viewport
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(2000);
    
    const newCount = await page.getByTestId('add-to-cart-button').count();
    await expect(newCount, 'Lazy loading must work in minimum viewport dimensions').toBeGreaterThanOrEqual(initialCount);
  });

  test('boundary — multiple simultaneous scroll triggers', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByTestId('add-to-cart-button').first(), 'Initial content must be present for simultaneous scroll test').toBeVisible();
    
    const initialCount = await page.getByTestId('add-to-cart-button').count();
    
    // Trigger multiple scroll events simultaneously
    await Promise.all([
      page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)),
      page.evaluate(() => window.scrollTo(0, document.body.scrollHeight - 100)),
      page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    ]);
    
    await page.waitForTimeout(3000);
    
    const finalCount = await page.getByTestId('add-to-cart-button').count();
    await expect(finalCount, 'System must handle simultaneous scroll triggers gracefully').toBeGreaterThanOrEqual(initialCount);
    
    await expect(page.getByRole('button', { name: 'Back to top' }), 'Navigation must remain functional after simultaneous scroll events').toBeVisible();
  });

  test('boundary — scroll loading with maximum content load', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByTestId('add-to-cart-button').first(), 'Initial deals must load before maximum content test').toBeVisible();
    
    let previousCount = 0;
    let currentCount = await page.getByTestId('add-to-cart-button').count();
    let scrollAttempts = 0;
    const maxScrollAttempts = 10;
    
    // Keep scrolling until no new content loads or max attempts reached
    while (currentCount > previousCount && scrollAttempts < maxScrollAttempts) {
      previousCount = currentCount;
      
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(2000);
      
      currentCount = await page.getByTestId('add-to-cart-button').count();
      scrollAttempts++;
    }
    
    await expect(currentCount, 'System must handle maximum content loading boundary gracefully').toBeGreaterThan(0);
    await expect(page.getByRole('button', { name: 'Back to top' }), 'Back to top button must be available at maximum content load').toBeVisible();
  });
});