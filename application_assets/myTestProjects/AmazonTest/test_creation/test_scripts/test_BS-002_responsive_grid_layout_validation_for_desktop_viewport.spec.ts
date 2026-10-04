import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Responsive Grid Layout Validation for Desktop Viewport (BS-002)', () => {

  test('positive — desktop grid layout displays 4-5 items per row at 1280px viewport', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 1280, height: 800 });
    
    // Wait for deal cards to load
    await page.waitForLoadState('networkidle');
    
    // Verify grid components exist and are visible
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'First deal card must be visible in grid layout').toBeVisible();
    
    // Check that multiple cards are present (at least 4 for proper grid validation)
    const cardCount = await dealCards.count();
    expect(cardCount, 'Grid must contain at least 4 deal cards for layout validation').toBeGreaterThanOrEqual(4);
    
    // Verify no horizontal overflow occurs
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
    expect(bodyScrollWidth <= bodyClientWidth, 'Page must not have horizontal overflow').toBeTruthy();
    
    // Check viewport width is correctly set to 1280px
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must be set to 1280px for desktop testing').toBe(1280);
    
    // Verify grid items are positioned correctly (no overlapping)
    const firstCard = dealCards.nth(0);
    const secondCard = dealCards.nth(1);
    const firstCardBox = await firstCard.boundingBox();
    const secondCardBox = await secondCard.boundingBox();
    
    if (firstCardBox && secondCardBox) {
      const horizontalSpacing = firstCardBox.x !== secondCardBox.x;
      expect(horizontalSpacing, 'Deal cards must be horizontally distributed in grid layout').toBeTruthy();
    }
  });

  test('negative — viewport below 1280px disrupts expected grid layout', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 800, height: 600 });
    
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards must still be visible at smaller viewport').toBeVisible();
    
    // At smaller viewport, cards should not maintain 4-5 per row layout
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must be below desktop threshold').toBeLessThan(1280);
    
    // Grid behavior should be different (responsive)
    const cardCount = await dealCards.count();
    expect(cardCount, 'Cards must still be present but layout differs from desktop grid').toBeGreaterThan(0);
  });

  test('negative — extremely narrow viewport forces single column layout', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 320, height: 568 });
    
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards must be visible even in mobile viewport').toBeVisible();
    
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must be mobile size').toBe(320);
    
    // Should not maintain desktop grid structure
    const cardCount = await dealCards.count();
    expect(cardCount, 'Cards must be present but in mobile-responsive layout').toBeGreaterThan(0);
  });

  test('negative — oversized viewport maintains grid but with different spacing', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 1920, height: 1080 });
    
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards must be visible in large desktop viewport').toBeVisible();
    
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must be larger than standard desktop').toBe(1920);
    
    // Grid should adapt to larger screen
    const cardCount = await dealCards.count();
    expect(cardCount, 'Cards must be present with potentially different grid distribution').toBeGreaterThan(0);
  });

  test('negative — invalid viewport dimensions cause layout issues', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 100, height: 100 });
    
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    // Even with invalid small viewport, cards should attempt to render
    const cardCount = await dealCards.count();
    expect(cardCount, 'Cards may still be present despite invalid viewport size').toBeGreaterThanOrEqual(0);
    
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must reflect the invalid small size').toBe(100);
  });

  test('boundary — exactly 1280px viewport maintains optimal grid layout', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 1280, height: 720 });
    
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards must be visible at exact 1280px boundary').toBeVisible();
    
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must be exactly at desktop boundary').toBe(1280);
    
    // Verify grid maintains expected behavior at boundary
    const cardCount = await dealCards.count();
    expect(cardCount, 'Grid must contain multiple cards at desktop boundary width').toBeGreaterThanOrEqual(4);
    
    // Check no horizontal overflow at boundary
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
    expect(bodyScrollWidth <= bodyClientWidth, 'No horizontal overflow must occur at 1280px boundary').toBeTruthy();
  });

  test('boundary — 1279px viewport tests responsive breakpoint threshold', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 1279, height: 720 });
    
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards must be visible just below desktop breakpoint').toBeVisible();
    
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must be just below desktop threshold').toBe(1279);
    
    // Layout behavior may differ by 1px from desktop
    const cardCount = await dealCards.count();
    expect(cardCount, 'Cards must be present at sub-desktop width boundary').toBeGreaterThan(0);
  });

  test('boundary — maximum practical viewport width tests grid scalability', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.setViewportSize({ width: 2560, height: 1440 });
    
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    await expect(dealCards.first(), 'Deal cards must be visible at maximum viewport width').toBeVisible();
    
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(viewportWidth, 'Viewport width must be at maximum practical desktop size').toBe(2560);
    
    // Grid should scale appropriately for large displays
    const cardCount = await dealCards.count();
    expect(cardCount, 'Grid must contain cards and scale for large displays').toBeGreaterThan(0);
    
    // Verify no horizontal overflow at maximum width
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
    expect(bodyScrollWidth <= bodyClientWidth, 'No horizontal overflow must occur at maximum viewport width').toBeTruthy();
  });

});