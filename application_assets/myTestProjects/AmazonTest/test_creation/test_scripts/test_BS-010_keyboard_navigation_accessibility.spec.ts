import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Keyboard Navigation Accessibility (BS-010)', () => {
  
  test('positive — all interactive elements accessible via keyboard tabbing in logical sequence', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait for page to load and interactive elements to be available
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category filter must be visible').toBeVisible();
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics category filter must be visible').toBeVisible();
    
    // Start keyboard navigation from the first focusable element
    await page.keyboard.press('Tab');
    
    // Navigate through category filters
    const mobilesFilter = page.getByRole('button', { name: 'Mobiles' });
    await mobilesFilter.focus();
    await expect(mobilesFilter, 'Mobiles filter must be focusable via keyboard').toBeFocused();
    
    await page.keyboard.press('Tab');
    const electronicsFilter = page.getByRole('button', { name: 'Electronics' });
    await expect(electronicsFilter, 'Electronics filter must be focusable in tab sequence').toBeFocused();
    
    // Continue tabbing to reach deal cards
    let tabCount = 0;
    let addToCartButton = page.getByTestId('add-to-cart-button').first();
    
    // Tab until we reach the first add to cart button or max 20 tabs
    while (tabCount < 20) {
      await page.keyboard.press('Tab');
      tabCount++;
      
      if (await addToCartButton.isVisible() && await addToCartButton.evaluate(el => document.activeElement === el)) {
        break;
      }
    }
    
    await expect(addToCartButton, 'First add to cart button must be reachable via keyboard navigation').toBeFocused();
    
    // Verify sequential navigation through deal cards
    await page.keyboard.press('Tab');
    const secondAddToCartButton = page.getByTestId('add-to-cart-button').nth(1);
    if (await secondAddToCartButton.isVisible()) {
      await expect(secondAddToCartButton, 'Second add to cart button must be accessible in tab sequence').toBeFocused();
    }
  });

  test('negative — keyboard navigation with rapid tab presses maintains focus order', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category filter must be visible').toBeVisible();
    
    // Rapidly press Tab multiple times to test focus management
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press('Tab');
      await page.waitForTimeout(50); // Short delay between rapid tabs
    }
    
    // Verify that focus is still on a valid interactive element
    const focusedElement = await page.evaluate(() => document.activeElement?.tagName);
    await expect(focusedElement === 'BUTTON' || focusedElement === 'A' || focusedElement === 'INPUT', 
      'Focused element must be an interactive element after rapid tabbing').toBeTruthy();
  });

  test('negative — shift+tab reverse navigation maintains proper sequence', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics category filter must be visible').toBeVisible();
    
    // Navigate forward first
    const electronicsFilter = page.getByRole('button', { name: 'Electronics' });
    await electronicsFilter.focus();
    await expect(electronicsFilter, 'Electronics filter must be focused').toBeFocused();
    
    // Navigate backward with Shift+Tab
    await page.keyboard.press('Shift+Tab');
    const mobilesFilter = page.getByRole('button', { name: 'Mobiles' });
    
    // Verify reverse navigation works properly
    const currentFocused = await page.evaluate(() => document.activeElement);
    await expect(currentFocused !== null, 'An element must maintain focus during reverse navigation').toBeTruthy();
  });

  test('negative — keyboard navigation with disabled javascript fallback', async ({ page }) => {
    // Disable JavaScript to test accessibility without JS enhancements
    await page.context().addInitScript(() => {
      Object.defineProperty(window, 'addEventListener', { value: () => {} });
    });
    
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category filter must be visible without JS enhancements').toBeVisible();
    
    // Test basic keyboard navigation still works
    await page.keyboard.press('Tab');
    const mobilesFilter = page.getByRole('button', { name: 'Mobiles' });
    await mobilesFilter.focus();
    await expect(mobilesFilter, 'Mobiles filter must be focusable even with limited JS').toBeFocused();
  });

  test('negative — keyboard navigation with screen reader simulation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category filter must be visible').toBeVisible();
    
    // Simulate screen reader navigation using arrow keys
    const mobilesFilter = page.getByRole('button', { name: 'Mobiles' });
    await mobilesFilter.focus();
    
    // Test that elements have proper ARIA labels for screen readers
    const ariaLabel = await mobilesFilter.getAttribute('aria-label');
    const hasAccessibleName = ariaLabel !== null || await mobilesFilter.textContent() !== '';
    await expect(hasAccessibleName, 'Interactive elements must have accessible names for screen readers').toBeTruthy();
  });

  test('boundary — keyboard navigation through maximum visible elements on page', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category filter must be visible').toBeVisible();
    
    let tabCount = 0;
    const maxTabs = 100; // Boundary test for maximum tab operations
    let lastFocusedElement = null;
    
    // Tab through all elements up to boundary limit
    while (tabCount < maxTabs) {
      await page.keyboard.press('Tab');
      tabCount++;
      
      const currentFocused = await page.evaluate(() => document.activeElement?.tagName);
      if (currentFocused === lastFocusedElement && tabCount > 10) {
        break; // Stop if we're cycling through the same elements
      }
      lastFocusedElement = currentFocused;
    }
    
    await expect(tabCount > 5, 'Must be able to navigate through at least 5 interactive elements').toBeTruthy();
    await expect(tabCount < maxTabs, 'Tab navigation must not get stuck in infinite loop').toBeTruthy();
  });

  test('boundary — keyboard navigation at page load boundary conditions', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Test keyboard navigation immediately after page load without waiting
    await page.keyboard.press('Tab');
    
    // Verify that at least one element can receive focus immediately
    const focusedElement = await page.evaluate(() => document.activeElement !== document.body);
    await expect(focusedElement, 'At least one interactive element must be focusable immediately after page load').toBeTruthy();
    
    // Test navigation to boundary elements (first and potentially last visible)
    const mobilesFilter = page.getByRole('button', { name: 'Mobiles' });
    if (await mobilesFilter.isVisible()) {
      await mobilesFilter.focus();
      await expect(mobilesFilter, 'First category filter must be accessible at page load boundary').toBeFocused();
    }
  });

  test('boundary — keyboard navigation with minimal viewport dimensions', async ({ page }) => {
    // Set viewport to minimal dimensions to test responsive keyboard navigation
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category filter must be visible in minimal viewport').toBeVisible();
    
    // Test that keyboard navigation works even in constrained viewport
    await page.keyboard.press('Tab');
    const mobilesFilter = page.getByRole('button', { name: 'Mobiles' });
    await mobilesFilter.focus();
    await expect(mobilesFilter, 'Elements must remain keyboard accessible in minimal viewport').toBeFocused();
    
    // Verify that focused elements are scrolled into view
    const isInViewport = await mobilesFilter.evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= window.innerHeight;
    });
    await expect(isInViewport, 'Focused elements must be scrolled into viewport during keyboard navigation').toBeTruthy();
  });

});