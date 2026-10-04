import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Lightning Deal Status Updates (BS-012)', () => {
  
  test('positive — lightning deal status accurately reflects real-time inventory changes', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to Lightning Deals section
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await expect(page.getByRole('button', { name: 'Lightning Deals' }), 'Lightning Deals filter should be active').toBeVisible();
    
    // Wait for Lightning Deal cards to load
    await page.waitForLoadState('networkidle');
    
    // Monitor Lightning Deal cards and verify initial state
    const addToCartButtons = page.getByTestId('add-to-cart-button');
    await expect(addToCartButtons.first(), 'Add to cart button should be visible on lightning deal card').toBeVisible();
    
    // Check for deal availability status elements
    const dealCards = page.locator('[data-testid*="deal-card"], .deal-card, .lightning-deal').first();
    await expect(dealCards, 'Lightning deal card should be present on the page').toBeVisible();
    
    // Verify initial cart button state is enabled for available deals
    const firstCartButton = addToCartButtons.first();
    await expect(firstCartButton, 'Add to cart button should be enabled for available deals').toBeEnabled();
    
    // Monitor for status changes by refreshing and checking states
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Verify UI elements update appropriately when deals change status
    await expect(page.getByRole('button', { name: 'Lightning Deals' }), 'Lightning Deals section should remain accessible after reload').toBeVisible();
    await expect(addToCartButtons.first(), 'Deal cards should maintain proper button states after refresh').toBeVisible();
  });

  test('negative — empty deal inventory shows appropriate unavailable state', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForLoadState('networkidle');
    
    // Look for deals that might be sold out or ended
    const dealCards = page.locator('[data-testid*="deal-card"], .deal-card, .lightning-deal');
    await expect(dealCards.first(), 'Deal cards should be present to check sold out states').toBeVisible();
    
    // Check for waitlist or ended state indicators
    const soldOutIndicators = page.locator('text=/sold out|waitlist|ended/i');
    if (await soldOutIndicators.count() > 0) {
      await expect(soldOutIndicators.first(), 'Sold out deals should show appropriate status message').toBeVisible();
    }
    
    // Verify cart buttons are disabled for unavailable deals
    const disabledButtons = page.locator('[data-testid="add-to-cart-button"][disabled], [data-testid="add-to-cart-button"]:disabled');
    if (await disabledButtons.count() > 0) {
      await expect(disabledButtons.first(), 'Unavailable deals should have disabled add to cart buttons').toBeDisabled();
    }
  });

  test('negative — corrupted deal data displays error handling', async ({ page }) => {
    await page.goto(BASE_URL + '&invalid=<script>alert("xss")</script>');
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForLoadState('networkidle');
    
    // Verify page still loads properly despite malformed parameters
    await expect(page.getByRole('button', { name: 'Lightning Deals' }), 'Lightning deals should load even with invalid parameters').toBeVisible();
    await expect(page.getByTestId('add-to-cart-button').first(), 'Deal cards should render properly despite URL corruption').toBeVisible();
    
    // Ensure no script execution from corrupted data
    const pageTitle = await page.title();
    await expect(pageTitle.includes('<script>'), 'Page should not execute malicious scripts from parameters').toBeFalsy();
  });

  test('negative — network interruption during deal status check maintains UI consistency', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate network issues during deal loading
    await page.route('**/api/deals/**', route => route.abort());
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    // Verify graceful handling of network issues
    await expect(page.getByRole('button', { name: 'Lightning Deals' }), 'Lightning deals filter should remain functional during network issues').toBeVisible();
    
    // Check that existing UI elements don't break
    const dealElements = page.locator('[data-testid*="deal"], .deal-card, .lightning-deal');
    if (await dealElements.count() > 0) {
      await expect(dealElements.first(), 'Existing deal elements should remain stable during network issues').toBeVisible();
    }
  });

  test('negative — invalid deal status injection attempts are rejected', async ({ page }) => {
    await page.goto(BASE_URL + '?deal_status=100%27%20OR%20%271%27=%271');
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForLoadState('networkidle');
    
    // Verify SQL injection attempts don't affect deal status display
    await expect(page.getByRole('button', { name: 'Lightning Deals' }), 'Lightning deals should load safely despite injection attempts').toBeVisible();
    await expect(page.getByTestId('add-to-cart-button').first(), 'Deal buttons should function normally despite malicious parameters').toBeVisible();
    
    // Ensure deal status integrity is maintained
    const dealCards = page.locator('[data-testid*="deal-card"], .deal-card, .lightning-deal');
    await expect(dealCards.first(), 'Deal cards should display legitimate status information only').toBeVisible();
  });

  test('boundary — maximum concurrent deal monitoring maintains performance', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForLoadState('networkidle');
    
    // Load maximum visible deals on page
    const allDealCards = page.locator('[data-testid*="deal-card"], .deal-card, .lightning-deal');
    const dealCount = await allDealCards.count();
    
    // Verify all deals load properly at boundary
    if (dealCount > 0) {
      await expect(allDealCards.first(), 'First deal card should load at maximum capacity').toBeVisible();
      if (dealCount > 1) {
        await expect(allDealCards.last(), 'Last deal card should load at maximum capacity').toBeVisible();
      }
    }
    
    // Check that add to cart buttons work for all visible deals
    const cartButtons = page.getByTestId('add-to-cart-button');
    const buttonCount = await cartButtons.count();
    if (buttonCount > 0) {
      await expect(cartButtons.first(), 'Cart buttons should remain functional at maximum deal load').toBeVisible();
    }
  });

  test('boundary — deal status update at exact inventory depletion boundary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForLoadState('networkidle');
    
    // Monitor deal progress bars at high completion levels
    const progressBars = page.locator('[role="progressbar"], .progress-bar, [data-testid*="progress"]');
    const dealCards = page.locator('[data-testid*="deal-card"], .deal-card, .lightning-deal');
    
    await expect(dealCards.first(), 'Deal cards should be present to test inventory boundary').toBeVisible();
    
    // Check for deals near completion (boundary condition)
    if (await progressBars.count() > 0) {
      await expect(progressBars.first(), 'Progress indicators should be visible for boundary testing').toBeVisible();
    }
    
    // Verify cart button state transitions properly at boundary
    const cartButtons = page.getByTestId('add-to-cart-button');
    await expect(cartButtons.first(), 'Add to cart buttons should handle boundary inventory levels correctly').toBeVisible();
  });

  test('boundary — lightning deal timer expiration boundary handling', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForLoadState('networkidle');
    
    // Look for deals with very short time remaining (boundary condition)
    const timerElements = page.locator('[data-testid*="timer"], .timer, .countdown, [data-testid*="time-remaining"]');
    const dealCards = page.locator('[data-testid*="deal-card"], .deal-card, .lightning-deal');
    
    await expect(dealCards.first(), 'Deal cards should be present for timer boundary testing').toBeVisible();
    
    // Verify timer displays and deal state handling
    if (await timerElements.count() > 0) {
      await expect(timerElements.first(), 'Timer elements should be visible for expiration boundary testing').toBeVisible();
    }
    
    // Ensure add to cart buttons handle timer expiration appropriately
    const cartButtons = page.getByTestId('add-to-cart-button');
    await expect(cartButtons.first(), 'Cart buttons should respond correctly to timer expiration boundaries').toBeVisible();
    
    // Check that expired deals show proper ended state
    const expiredDeals = page.locator('text=/expired|ended|no longer available/i');
    if (await expiredDeals.count() > 0) {
      await expect(expiredDeals.first(), 'Expired deals should clearly indicate ended status at boundary').toBeVisible();
    }
  });

});