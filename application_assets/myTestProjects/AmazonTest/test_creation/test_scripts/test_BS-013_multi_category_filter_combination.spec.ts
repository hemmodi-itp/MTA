import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Multi-Category Filter Combination (BS-013)', () => {
  
  test('positive — selecting multiple category filters displays combined results with AJAX updates', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait for page to load and filters to be available
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles filter button should be visible').toBeVisible();
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics filter button should be visible').toBeVisible();
    
    // Monitor network requests to verify AJAX calls
    const ajaxRequests = [];
    page.on('request', request => {
      if (request.url().includes('deals') && request.method() === 'GET') {
        ajaxRequests.push(request.url());
      }
    });
    
    // Select first category filter
    await page.getByRole('button', { name: 'Mobiles' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles filter should appear selected after click').toHaveClass(/selected|active|checked/);
    
    // Select second category filter
    await page.getByRole('button', { name: 'Electronics' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics filter should appear selected after click').toHaveClass(/selected|active|checked/);
    
    // Select third category filter
    await page.getByRole('button', { name: 'Home & Kitchen' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByRole('button', { name: 'Home & Kitchen' }), 'Home & Kitchen filter should appear selected after click').toHaveClass(/selected|active|checked/);
    
    // Verify AJAX requests were made
    expect(ajaxRequests.length, 'AJAX requests should have been triggered for filter updates').toBeGreaterThan(0);
    
    // Verify deal results are displayed
    await expect(page.getByTestId('add-to-cart-button').first(), 'At least one deal with add-to-cart button should be visible in filtered results').toBeVisible();
  });

  test('negative — rapidly clicking filters with empty results handling', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles filter should be available for rapid clicking test').toBeVisible();
    
    // Rapidly click filters to test race conditions
    await page.getByRole('button', { name: 'Mobiles' }).click();
    await page.getByRole('button', { name: 'Electronics' }).click();
    await page.getByRole('button', { name: 'Home & Kitchen' }).click();
    await page.getByRole('button', { name: 'Mobiles' }).click(); // Deselect
    
    await page.waitForLoadState('networkidle');
    
    // Should handle the rapid state changes gracefully
    const hasResults = await page.getByTestId('add-to-cart-button').first().isVisible();
    const hasNoResults = await page.getByText('No deals found').isVisible();
    
    expect(hasResults || hasNoResults, 'Page should show either results or no results message after rapid filter changes').toBeTruthy();
  });

  test('negative — filter selection with malformed URL parameters', async ({ page }) => {
    // Navigate with malformed filter parameters
    await page.goto(`${BASE_URL}&category=<script>alert('xss')</script>&filter=';DROP TABLE deals;--`);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Filter buttons should still be available despite malformed URL params').toBeVisible();
    
    // Try to select filters normally
    await page.getByRole('button', { name: 'Electronics' }).click();
    await page.waitForLoadState('networkidle');
    
    // Page should handle malformed parameters gracefully
    const pageTitle = await page.title();
    expect(pageTitle, 'Page title should not contain script injection content').not.toContain('<script>');
    expect(pageTitle, 'Page title should not contain SQL injection content').not.toContain('DROP TABLE');
  });

  test('negative — filter interaction with disabled JavaScript simulation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Disable JavaScript to test graceful degradation
    await page.context().addInitScript(() => {
      Object.defineProperty(window, 'XMLHttpRequest', { value: undefined });
      Object.defineProperty(window, 'fetch', { value: undefined });
    });
    
    await page.reload();
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Filter buttons should be present even without AJAX capability').toBeVisible();
    
    // Click filter without AJAX support
    await page.getByRole('button', { name: 'Mobiles' }).click();
    
    // Should either show results or graceful fallback
    const hasContent = await page.locator('body').textContent();
    expect(hasContent, 'Page should maintain functionality without JavaScript AJAX calls').toContain('deals');
  });

  test('negative — simultaneous filter selection causing server errors', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Intercept requests to simulate server errors
    await page.route('**/deals*', route => {
      if (Math.random() > 0.5) {
        route.fulfill({ status: 500, body: 'Server Error' });
      } else {
        route.continue();
      }
    });
    
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics filter should be available for error simulation test').toBeVisible();
    
    // Select multiple filters that might trigger server errors
    await page.getByRole('button', { name: 'Electronics' }).click();
    await page.getByRole('button', { name: 'Home & Kitchen' }).click();
    
    await page.waitForTimeout(2000); // Allow time for potential error handling
    
    // Page should handle server errors gracefully
    const errorElements = page.getByText(/error|sorry|try again/i);
    const hasResults = await page.getByTestId('add-to-cart-button').first().isVisible();
    const hasError = await errorElements.first().isVisible();
    
    expect(hasResults || hasError, 'Page should show either results or error message when server errors occur').toBeTruthy();
  });

  test('boundary — maximum number of simultaneous filter selections', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const filters = [
      page.getByRole('button', { name: 'Mobiles' }),
      page.getByRole('button', { name: 'Electronics' }),
      page.getByRole('button', { name: 'Home & Kitchen' })
    ];
    
    // Verify all boundary filters are available
    for (const filter of filters) {
      await expect(filter, 'Each filter button should be visible for boundary testing').toBeVisible();
    }
    
    // Select all available filters to test maximum combinations
    for (const filter of filters) {
      await filter.click();
      await page.waitForTimeout(500); // Brief pause between selections
    }
    
    await page.waitForLoadState('networkidle');
    
    // Should handle maximum filter combinations
    const allFiltersSelected = await Promise.all(
      filters.map(filter => filter.getAttribute('class'))
    );
    
    expect(allFiltersSelected.some(cls => cls?.includes('selected') || cls?.includes('active')), 'At least some filters should remain selected at boundary limit').toBeTruthy();
  });

  test('boundary — filter selection with extremely long URL parameters', async ({ page }) => {
    const longCategory = 'A'.repeat(2000);
    const longUrl = `${BASE_URL}&category=${longCategory}&filter=${'B'.repeat(1000)}`;
    
    await page.goto(longUrl);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Filter interface should handle extremely long URL parameters').toBeVisible();
    
    // Select filters with long URL context
    await page.getByRole('button', { name: 'Electronics' }).click();
    await page.waitForLoadState('networkidle');
    
    // URL should be handled without breaking functionality
    const currentUrl = page.url();
    expect(currentUrl.length, 'URL length should be manageable even with long parameters').toBeLessThan(8192); // Typical URL limit
    
    // Results should still be functional
    const hasResults = await page.getByTestId('add-to-cart-button').first().isVisible();
    const hasNoResults = await page.getByText(/no.*deals|no.*results/i).first().isVisible();
    
    expect(hasResults || hasNoResults, 'Page should show appropriate content despite long URL parameters').toBeTruthy();
  });

  test('boundary — rapid filter toggle at performance limits', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles filter should be ready for performance boundary testing').toBeVisible();
    
    const startTime = Date.now();
    
    // Rapidly toggle filters 20 times to test performance boundaries
    for (let i = 0; i < 20; i++) {
      await page.getByRole('button', { name: 'Mobiles' }).click();
      await page.getByRole('button', { name: 'Electronics' }).click();
      await page.getByRole('button', { name: 'Mobiles' }).click(); // Toggle off
      await page.getByRole('button', { name: 'Electronics' }).click(); // Toggle off
    }
    
    const endTime = Date.now();
    const totalTime = endTime - startTime;
    
    await page.waitForLoadState('networkidle');
    
    expect(totalTime, 'Rapid filter operations should complete within reasonable time boundary').toBeLessThan(30000); // 30 seconds max
    
    // Interface should remain responsive
    await expect(page.getByRole('button', { name: 'Home & Kitchen' }), 'Filter interface should remain responsive after performance stress test').toBeVisible();
  });
});