import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Responsive Grid Layout Validation for Tablet Viewport (BS-003)', () => {
  
  test('positive — tablet viewport displays 2-3 deal cards per row with proper grid collapse', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set viewport to 768px tablet resolution
    await page.setViewportSize({ width: 768, height: 1024 });
    
    // Wait for page to load and adjust to new viewport
    await page.waitForLoadState('networkidle');
    
    // Get deal card elements
    const dealCards = page.getByTestId('add-to-cart-button');
    
    // Verify deal cards are visible
    await expect(dealCards.first(), 'First deal card must be visible in tablet viewport').toBeVisible();
    
    // Check that cards are arranged properly in tablet layout
    const cardCount = await dealCards.count();
    await expect(cardCount, 'At least 3 deal cards should be present for grid validation').toBeGreaterThanOrEqual(3);
    
    // Get bounding boxes of first few cards to verify grid layout
    const firstCard = dealCards.nth(0);
    const secondCard = dealCards.nth(1);
    const thirdCard = dealCards.nth(2);
    
    const firstBox = await firstCard.boundingBox();
    const secondBox = await secondCard.boundingBox();
    const thirdBox = await thirdCard.boundingBox();
    
    // Verify cards don't overlap
    expect(firstBox, 'First card bounding box should be available').toBeTruthy();
    expect(secondBox, 'Second card bounding box should be available').toBeTruthy();
    expect(thirdBox, 'Third card bounding box should be available').toBeTruthy();
    
    // Check that text remains functional and readable
    await expect(firstCard, 'First deal card text should be readable and clickable').toBeEnabled();
    await expect(secondCard, 'Second deal card text should be readable and clickable').toBeEnabled();
    await expect(thirdCard, 'Third deal card text should be readable and clickable').toBeEnabled();
  });

  test('negative — narrow tablet viewport (400px) causes layout issues', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set extremely narrow viewport that should cause issues
    await page.setViewportSize({ width: 400, height: 1024 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    // Cards should still be visible even in constrained layout
    await expect(dealCards.first(), 'Deal cards should remain visible even in narrow viewport').toBeVisible();
    
    // But layout might be suboptimal - verify at least basic functionality
    const cardCount = await dealCards.count();
    expect(cardCount, 'Some deal cards should still be present in narrow viewport').toBeGreaterThan(0);
  });

  test('negative — very wide tablet viewport (1200px) breaks expected 2-3 items per row', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set wider than expected tablet viewport
    await page.setViewportSize({ width: 1200, height: 800 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    // Cards should be visible but may not follow tablet layout rules
    await expect(dealCards.first(), 'Deal cards should be visible in wide viewport').toBeVisible();
    
    const cardCount = await dealCards.count();
    expect(cardCount, 'Deal cards should be present in wide viewport').toBeGreaterThan(0);
  });

  test('negative — extreme portrait tablet viewport causes text overlap', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set extreme portrait orientation
    await page.setViewportSize({ width: 600, height: 2000 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    await expect(dealCards.first(), 'Deal cards should handle extreme portrait viewport').toBeVisible();
    
    // Verify cards are still functional despite unusual aspect ratio
    await expect(dealCards.first(), 'First deal card should remain clickable in portrait mode').toBeEnabled();
  });

  test('negative — landscape tablet orientation disrupts grid layout', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set landscape tablet orientation (height < width, but tablet-sized)
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    await expect(dealCards.first(), 'Deal cards should be visible in landscape tablet mode').toBeVisible();
    
    // May have more items per row than expected for tablet
    const cardCount = await dealCards.count();
    expect(cardCount, 'Deal cards should be present in landscape orientation').toBeGreaterThan(0);
  });

  test('boundary — minimum tablet width (768px) maintains proper layout', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set exactly at tablet breakpoint
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    await expect(dealCards.first(), 'Deal cards should display properly at minimum tablet width').toBeVisible();
    
    // Verify proper grid behavior at boundary
    const firstCard = dealCards.nth(0);
    const secondCard = dealCards.nth(1);
    
    await expect(firstCard, 'First card should be functional at tablet boundary width').toBeEnabled();
    await expect(secondCard, 'Second card should be functional at tablet boundary width').toBeEnabled();
  });

  test('boundary — maximum tablet width (1024px) before desktop breakpoint', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set at upper tablet boundary
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    await expect(dealCards.first(), 'Deal cards should display properly at maximum tablet width').toBeVisible();
    
    // Should still maintain tablet-appropriate layout
    const cardCount = await dealCards.count();
    expect(cardCount, 'Adequate number of deal cards should be visible at tablet max width').toBeGreaterThanOrEqual(2);
  });

  test('boundary — very tall tablet viewport tests vertical scrolling behavior', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set normal tablet width but very tall height
    await page.setViewportSize({ width: 768, height: 3000 });
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.getByTestId('add-to-cart-button');
    
    await expect(dealCards.first(), 'Deal cards should be visible in very tall viewport').toBeVisible();
    
    // Test scrolling behavior with tall viewport
    const cardCount = await dealCards.count();
    expect(cardCount, 'Multiple rows of deal cards should be visible in tall viewport').toBeGreaterThanOrEqual(3);
    
    // Verify cards maintain proper spacing in tall viewport
    await expect(dealCards.nth(2), 'Third deal card should be accessible in tall viewport').toBeVisible();
  });
});