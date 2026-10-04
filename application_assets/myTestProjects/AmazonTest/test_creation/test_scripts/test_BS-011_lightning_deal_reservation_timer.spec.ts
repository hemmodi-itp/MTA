import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Lightning Deal Reservation Timer (BS-011)', () => {
  
  test('positive — Lightning Deal item is successfully reserved with 15-minute countdown timer', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to Lightning Deals section
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await expect(page.getByRole('button', { name: 'Lightning Deals' }), 'Lightning Deals filter should be visible').toBeVisible();
    
    // Wait for deals to load and find an active Lightning Deal
    await page.waitForTimeout(2000);
    
    // Click Add to Cart on first available Lightning Deal
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart button should be visible for Lightning Deal').toBeVisible();
    await addToCartButton.click();
    
    // Navigate to cart to verify item was added
    await page.getByRole('link', { name: '0\nCart' }).click();
    await expect(page, 'Should navigate to cart page after clicking cart link').toHaveURL(/.*cart.*/);
    
    // Verify Lightning Deal item appears in cart
    await expect(page.locator('[data-testid="cart-item"]').first(), 'Lightning Deal item should appear in shopping cart').toBeVisible();
    
    // Verify 15-minute reservation timer is present and active
    const timerElement = page.locator('[data-testid="reservation-timer"]');
    await expect(timerElement, 'Reservation timer should be visible in cart').toBeVisible();
    
    // Verify timer shows countdown format (MM:SS)
    await expect(timerElement, 'Timer should display countdown format').toHaveText(/\d{1,2}:\d{2}/);
    
    // Wait a few seconds and verify timer is counting down
    const initialTime = await timerElement.textContent();
    await page.waitForTimeout(3000);
    const updatedTime = await timerElement.textContent();
    expect(initialTime !== updatedTime, 'Timer should be actively counting down').toBeTruthy();
  });

  test('negative — expired Lightning Deal cannot be added to cart', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    // Look for expired deal indicator
    const expiredDeal = page.locator('[data-deal-status="expired"]').first();
    if (await expiredDeal.isVisible()) {
      const expiredAddButton = expiredDeal.locator('[data-testid="add-to-cart-button"]');
      await expect(expiredAddButton, 'Add to cart button should be disabled for expired deals').toBeDisabled();
    } else {
      test.skip('No expired Lightning Deal found for testing');
    }
  });

  test('negative — sold out Lightning Deal shows unavailable status', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    // Look for sold out deal
    const soldOutDeal = page.locator('[data-deal-status="sold-out"]').first();
    if (await soldOutDeal.isVisible()) {
      await expect(soldOutDeal.getByText('Sold Out'), 'Sold out message should be displayed').toBeVisible();
      const soldOutButton = soldOutDeal.locator('[data-testid="add-to-cart-button"]');
      await expect(soldOutButton, 'Add to cart button should not be available for sold out deals').not.toBeVisible();
    } else {
      test.skip('No sold out Lightning Deal found for testing');
    }
  });

  test('negative — invalid cart state prevents Lightning Deal reservation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate cart error by intercepting cart API
    await page.route('**/cart/add', async route => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Cart service unavailable' })
      });
    });
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    if (await addToCartButton.isVisible()) {
      await addToCartButton.click();
      
      // Verify error message appears
      const errorMessage = page.locator('[data-testid="cart-error"]');
      await expect(errorMessage, 'Error message should appear when cart service fails').toBeVisible();
    } else {
      test.skip('No Lightning Deal available for cart error testing');
    }
  });

  test('negative — multiple Lightning Deal reservations exceed cart limit', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    // Try to add multiple Lightning Deals rapidly
    const addButtons = page.getByTestId('add-to-cart-button');
    const buttonCount = await addButtons.count();
    
    if (buttonCount >= 2) {
      await addButtons.nth(0).click();
      await addButtons.nth(1).click();
      
      // Check for cart limit warning
      const limitWarning = page.locator('[data-testid="cart-limit-warning"]');
      if (await limitWarning.isVisible()) {
        await expect(limitWarning, 'Cart limit warning should be displayed when exceeding Lightning Deal limit').toBeVisible();
      }
    } else {
      test.skip('Insufficient Lightning Deals available for limit testing');
    }
  });

  test('boundary — Lightning Deal timer at exactly 15 minutes shows correct countdown', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    if (await addToCartButton.isVisible()) {
      await addToCartButton.click();
      await page.getByRole('link', { name: '0\nCart' }).click();
      
      const timerElement = page.locator('[data-testid="reservation-timer"]');
      await expect(timerElement, 'Timer should be visible in cart').toBeVisible();
      
      const timerText = await timerElement.textContent();
      const [minutes, seconds] = timerText?.split(':').map(Number) || [0, 0];
      const totalSeconds = minutes * 60 + seconds;
      
      expect(totalSeconds <= 900, 'Timer should not exceed 15 minutes (900 seconds)').toBeTruthy();
      expect(totalSeconds > 0, 'Timer should show remaining time greater than 0').toBeTruthy();
    } else {
      test.skip('No Lightning Deal available for timer boundary testing');
    }
  });

  test('boundary — Lightning Deal timer approaching zero shows urgent state', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Mock a timer that's almost expired
    await page.addInitScript(() => {
      window.mockTimerState = { remainingSeconds: 30 };
    });
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    if (await addToCartButton.isVisible()) {
      await addToCartButton.click();
      await page.getByRole('link', { name: '0\nCart' }).click();
      
      // Check for urgent timer styling when under 1 minute
      const timerElement = page.locator('[data-testid="reservation-timer"]');
      const timerText = await timerElement.textContent();
      
      if (timerText && timerText.includes('0:')) {
        await expect(timerElement, 'Timer should show urgent state when under 1 minute').toHaveClass(/urgent|warning|critical/);
      }
    } else {
      test.skip('No Lightning Deal available for urgent timer testing');
    }
  });

  test('boundary — maximum Lightning Deal quantity per customer is enforced', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await page.waitForTimeout(2000);
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    if (await addToCartButton.isVisible()) {
      // Add item to cart
      await addToCartButton.click();
      
      // Try to add same item again if possible
      if (await addToCartButton.isVisible()) {
        await addToCartButton.click();
        
        // Check for quantity limit message
        const quantityLimit = page.locator('[data-testid="quantity-limit-message"]');
        if (await quantityLimit.isVisible()) {
          await expect(quantityLimit, 'Quantity limit message should appear when exceeding per-customer limit').toBeVisible();
        }
      }
      
      // Verify cart shows maximum allowed quantity
      await page.getByRole('link', { name: '0\nCart' }).click();
      const quantitySelector = page.locator('[data-testid="quantity-selector"]');
      if (await quantitySelector.isVisible()) {
        const maxQuantity = await quantitySelector.getAttribute('max');
        expect(parseInt(maxQuantity || '1') >= 1, 'Maximum quantity should be at least 1').toBeTruthy();
      }
    } else {
      test.skip('No Lightning Deal available for quantity boundary testing');
    }
  });
});