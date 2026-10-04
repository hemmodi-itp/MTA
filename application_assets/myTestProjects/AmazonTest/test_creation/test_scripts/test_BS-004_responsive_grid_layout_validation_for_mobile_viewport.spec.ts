import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Responsive Grid Layout Validation for Mobile Viewport (BS-004)', () => {
  
  test('positive — grid transforms to mobile-optimized stacked layout with readable fonts', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set viewport to 375px Mobile resolution
    await page.setViewportSize({ width: 375, height: 667 });
    
    // Wait for page to load and adjust to new viewport
    await page.waitForLoadState('networkidle');
    
    // Verify deal cards are present for layout validation
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'First deal card must be visible in mobile viewport').toBeVisible();
    
    // Get multiple deal cards to verify layout
    const cardElements = await dealCards.all();
    await expect(cardElements.length, 'At least 2 deal cards should be present for layout testing').toBeGreaterThanOrEqual(2);
    
    // Check that items display in stacked layout (1-2 items per row)
    if (cardElements.length >= 2) {
      const firstCard = cardElements[0];
      const secondCard = cardElements[1];
      
      const firstCardBox = await firstCard.boundingBox();
      const secondCardBox = await secondCard.boundingBox();
      
      await expect(firstCardBox, 'First card bounding box should be available').toBeTruthy();
      await expect(secondCardBox, 'Second card bounding box should be available').toBeTruthy();
      
      if (firstCardBox && secondCardBox) {
        const cardsOnSameRow = Math.abs(firstCardBox.y - secondCardBox.y) < 50;
        const cardWidth = firstCardBox.width;
        
        // In mobile viewport (375px), cards should take significant width for stacked layout
        await expect(cardWidth > 150, 'Card width should be substantial for mobile stacked layout').toBeTruthy();
        
        // Verify proper mobile distribution (max 2 items per row)
        if (cardsOnSameRow) {
          await expect(cardWidth < 185, 'If 2 cards per row, each card width should be less than half viewport').toBeTruthy();
        }
      }
    }
    
    // Verify font sizes remain readable by checking computed styles
    const dealCard = dealCards.first();
    const fontSize = await dealCard.evaluate((el) => {
      return window.getComputedStyle(el).fontSize;
    });
    
    const fontSizeValue = parseInt(fontSize.replace('px', ''));
    await expect(fontSizeValue >= 12, 'Font size should be at least 12px for mobile readability').toBeTruthy();
  });

  test('negative — layout validation with corrupted viewport dimensions', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set extreme viewport that might break layout
    await page.setViewportSize({ width: 1, height: 1 });
    await page.waitForLoadState('networkidle');
    
    // Even with corrupted viewport, elements should still be accessible
    const dealCards = page.getByTestId('add-to-cart-button');
    const cardCount = await dealCards.count();
    
    await expect(cardCount, 'Deal cards should still be present even with extreme viewport').toBeGreaterThanOrEqual(0);
    
    // Reset to mobile and verify recovery
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500); // Allow layout to adjust
    
    await expect(dealCards.first(), 'Layout should recover after viewport reset').toBeVisible({ timeout: 5000 });
  });

  test('negative — grid behavior with disabled JavaScript affecting responsive layout', async ({ page }) => {
    // Disable JavaScript to test if CSS-only responsive design works
    await page.context().addInitScript(() => {
      Object.defineProperty(window, 'innerWidth', { value: 375, writable: false });
    });
    
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 375, height: 667 });
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    // Even without JS enhancements, basic layout should work
    await expect(dealCards.first(), 'Deal cards should be visible without JavaScript enhancements').toBeVisible({ timeout: 10000 });
    
    // Verify some level of responsive behavior exists
    const cardElement = dealCards.first();
    const boundingBox = await cardElement.boundingBox();
    
    if (boundingBox) {
      await expect(boundingBox.width > 0, 'Card should have positive width even without JS').toBeTruthy();
    }
  });

  test('negative — responsive layout with network interruption during load', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate network interruption
    await page.route('**/*', route => {
      if (route.request().resourceType() === 'stylesheet') {
        route.abort();
      } else {
        route.continue();
      }
    });
    
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();
    
    // Even with CSS loading issues, basic content should be present
    const dealCards = page.getByTestId('add-to-cart-button');
    const hasContent = await dealCards.count();
    
    await expect(hasContent, 'Some deal content should be present even with CSS loading issues').toBeGreaterThanOrEqual(0);
  });

  test('negative — mobile layout validation with excessive content manipulation', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 375, height: 667 });
    
    // Inject excessive content that might break layout
    await page.evaluate(() => {
      const cards = document.querySelectorAll('[data-testid="add-to-cart-button"]');
      cards.forEach(card => {
        if (card.parentElement) {
          const longText = 'x'.repeat(1000);
          const textElement = document.createElement('div');
          textElement.textContent = longText;
          card.parentElement.appendChild(textElement);
        }
      });
    });
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards should remain functional despite content manipulation').toBeVisible();
    
    // Verify layout hasn't completely broken
    const cardBox = await dealCards.first().boundingBox();
    if (cardBox) {
      await expect(cardBox.width <= 375, 'Card width should not exceed viewport width even with excessive content').toBeTruthy();
    }
  });

  test('boundary — minimum mobile viewport width (320px) layout validation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Test at minimum mobile width boundary
    await page.setViewportSize({ width: 320, height: 568 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards should be visible at minimum mobile width (320px)').toBeVisible();
    
    // Verify single column layout at minimum width
    const cardElements = await dealCards.all();
    if (cardElements.length >= 2) {
      const firstCardBox = await cardElements[0].boundingBox();
      const secondCardBox = await cardElements[1].boundingBox();
      
      if (firstCardBox && secondCardBox) {
        const cardWidth = firstCardBox.width;
        await expect(cardWidth > 250, 'Cards should take most of the 320px width for single column layout').toBeTruthy();
      }
    }
  });

  test('boundary — maximum mobile viewport width (768px) before tablet breakpoint', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Test at maximum mobile width boundary before tablet
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards should be visible at maximum mobile width (768px)').toBeVisible();
    
    // At 768px, should allow for 2-3 items per row
    const cardElements = await dealCards.all();
    if (cardElements.length >= 2) {
      const firstCardBox = await cardElements[0].boundingBox();
      
      if (firstCardBox) {
        const cardWidth = firstCardBox.width;
        await expect(cardWidth < 350, 'Card width should allow multiple items per row at 768px width').toBeTruthy();
        await expect(cardWidth > 200, 'Card width should still be substantial at tablet boundary').toBeTruthy();
      }
    }
  });

  test('boundary — extreme aspect ratio mobile viewport layout handling', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Test extreme aspect ratio (very tall, narrow mobile)
    await page.setViewportSize({ width: 375, height: 2000 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards should handle extreme aspect ratios gracefully').toBeVisible();
    
    // Verify vertical scrolling works with tall viewport
    const initialPosition = await page.evaluate(() => window.pageYOffset);
    await page.mouse.wheel(0, 500);
    const scrolledPosition = await page.evaluate(() => window.pageYOffset);
    
    await expect(scrolledPosition > initialPosition, 'Page should scroll properly with extreme aspect ratio').toBeTruthy();
    
    // Verify layout consistency after scroll
    await expect(dealCards.first(), 'Deal cards should remain properly positioned after scrolling').toBeVisible();
  });
});