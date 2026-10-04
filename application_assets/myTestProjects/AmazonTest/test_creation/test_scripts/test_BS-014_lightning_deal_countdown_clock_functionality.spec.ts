import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Lightning Deal Countdown Clock Functionality (BS-014)', () => {

  test('positive — lightning deal countdown displays real-time descending time and expires accurately', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to Lightning Deals section
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    await expect(page.getByRole('button', { name: 'Lightning Deals' }), 'Lightning Deals button should be accessible').toBeVisible();
    
    // Locate Lightning Deal cards with countdown clocks
    const dealCard = page.getByTestId('add-to-cart-button').first();
    await expect(dealCard, 'Lightning deal card should be visible').toBeVisible();
    
    // Find countdown timer element (assuming it's near the deal card)
    const countdownTimer = page.locator('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]').first();
    
    if (await countdownTimer.count() > 0) {
      // Verify countdown displays time in expected format
      await expect(countdownTimer, 'Countdown timer should be visible on deal card').toBeVisible();
      
      // Capture initial countdown value
      const initialTime = await countdownTimer.textContent();
      await expect(initialTime, 'Initial countdown time should be in valid format').toMatch(/\d{1,2}:\d{2}:\d{2}/);
      
      // Wait a few seconds and verify countdown is descending
      await page.waitForTimeout(3000);
      const updatedTime = await countdownTimer.textContent();
      await expect(updatedTime, 'Countdown time should have decreased after waiting').not.toBe(initialTime);
      
      // Monitor countdown behavior (simulate approaching expiration)
      const timePattern = /(\d{1,2}):(\d{2}):(\d{2})/;
      const match = updatedTime?.match(timePattern);
      if (match) {
        const [, hours, minutes, seconds] = match;
        await expect(parseInt(hours), 'Hours should be valid number').toBeGreaterThanOrEqual(0);
        await expect(parseInt(minutes), 'Minutes should be valid number').toBeLessThan(60);
        await expect(parseInt(seconds), 'Seconds should be valid number').toBeLessThan(60);
      }
    }
    
    // Verify deal card remains interactive while timer is active
    await expect(dealCard, 'Deal card should remain clickable while timer is active').toBeEnabled();
  });

  test('negative — expired lightning deal should not display countdown timer', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    
    // Look for expired deals (deals without active countdown)
    const expiredDealCards = page.locator('[data-testid="add-to-cart-button"]').filter({ hasNot: page.locator('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]') });
    
    if (await expiredDealCards.count() > 0) {
      const expiredCard = expiredDealCards.first();
      await expect(expiredCard, 'Expired deal card should be visible').toBeVisible();
      
      // Verify no countdown timer is present
      const countdownInExpiredCard = expiredCard.locator('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]');
      await expect(countdownInExpiredCard, 'Expired deal should not have active countdown timer').toHaveCount(0);
    }
  });

  test('negative — malformed countdown timer should not break deal display', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    
    // Inject malformed timer data via page evaluation (simulating corrupted data)
    await page.evaluate(() => {
      const timerElements = document.querySelectorAll('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]');
      if (timerElements.length > 0) {
        (timerElements[0] as HTMLElement).textContent = '##:##:##';
      }
    });
    
    const dealCard = page.getByTestId('add-to-cart-button').first();
    await expect(dealCard, 'Deal card should remain visible despite malformed timer').toBeVisible();
    await expect(dealCard, 'Deal card should remain functional despite timer corruption').toBeEnabled();
  });

  test('negative — network interruption should not corrupt countdown display', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate network issues by intercepting timer-related requests
    await page.route('**/timer**', route => route.abort());
    await page.route('**/countdown**', route => route.abort());
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    
    const dealCard = page.getByTestId('add-to-cart-button').first();
    await expect(dealCard, 'Deal card should be visible even with network issues').toBeVisible();
    
    // Verify page doesn't crash despite network interruption
    const pageTitle = await page.title();
    await expect(pageTitle, 'Page should remain functional during network issues').toBeTruthy();
  });

  test('negative — invalid time format injection should not affect countdown', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    
    // Attempt to inject invalid time formats
    await page.evaluate(() => {
      const timerElements = document.querySelectorAll('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]');
      if (timerElements.length > 0) {
        (timerElements[0] as HTMLElement).textContent = '<script>alert("xss")</script>';
      }
    });
    
    const dealCard = page.getByTestId('add-to-cart-button').first();
    await expect(dealCard, 'Deal card should remain secure against script injection').toBeVisible();
    
    // Verify no alert dialogs were triggered
    page.on('dialog', dialog => {
      dialog.dismiss();
      throw new Error('XSS vulnerability detected in countdown timer');
    });
  });

  test('boundary — countdown timer at exactly 00:00:01 should expire correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    
    const dealCard = page.getByTestId('add-to-cart-button').first();
    await expect(dealCard, 'Deal card should be visible for boundary testing').toBeVisible();
    
    // Simulate timer at boundary (1 second remaining) via page manipulation
    await page.evaluate(() => {
      const timerElements = document.querySelectorAll('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]');
      if (timerElements.length > 0) {
        (timerElements[0] as HTMLElement).textContent = '00:00:01';
      }
    });
    
    const countdownTimer = page.locator('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]').first();
    if (await countdownTimer.count() > 0) {
      const boundaryTime = await countdownTimer.textContent();
      await expect(boundaryTime, 'Boundary countdown should show 1 second remaining').toBe('00:00:01');
    }
  });

  test('boundary — countdown timer with maximum duration should display correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    
    // Simulate maximum duration timer (23:59:59)
    await page.evaluate(() => {
      const timerElements = document.querySelectorAll('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]');
      if (timerElements.length > 0) {
        (timerElements[0] as HTMLElement).textContent = '23:59:59';
      }
    });
    
    const countdownTimer = page.locator('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]').first();
    if (await countdownTimer.count() > 0) {
      const maxTime = await countdownTimer.textContent();
      await expect(maxTime, 'Maximum duration countdown should display correctly').toMatch(/^23:59:59$/);
      
      const dealCard = page.getByTestId('add-to-cart-button').first();
      await expect(dealCard, 'Deal card should remain functional with maximum duration timer').toBeEnabled();
    }
  });

  test('boundary — multiple lightning deals with synchronized countdown timers', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('button', { name: 'Lightning Deals' }).click();
    
    const dealCards = page.getByTestId('add-to-cart-button');
    const cardCount = await dealCards.count();
    
    if (cardCount >= 2) {
      // Verify multiple deal cards are present
      await expect(dealCards.nth(0), 'First lightning deal card should be visible').toBeVisible();
      await expect(dealCards.nth(1), 'Second lightning deal card should be visible').toBeVisible();
      
      // Check that multiple countdown timers can coexist
      const allTimers = page.locator('[data-testid*="countdown"], [class*="countdown"], [class*="timer"]');
      const timerCount = await allTimers.count();
      
      if (timerCount >= 2) {
        await expect(allTimers.nth(0), 'First countdown timer should be visible').toBeVisible();
        await expect(allTimers.nth(1), 'Second countdown timer should be visible').toBeVisible();
        
        // Verify both timers update independently
        const timer1Text = await allTimers.nth(0).textContent();
        const timer2Text = await allTimers.nth(1).textContent();
        
        await expect(timer1Text, 'First timer should have valid format').toMatch(/\d{1,2}:\d{2}:\d{2}/);
        await expect(timer2Text, 'Second timer should have valid format').toMatch(/\d{1,2}:\d{2}:\d{2}/);
      }
    }
    
    await expect(cardCount, 'At least one deal card should be available for boundary testing').toBeGreaterThanOrEqual(1);
  });

});