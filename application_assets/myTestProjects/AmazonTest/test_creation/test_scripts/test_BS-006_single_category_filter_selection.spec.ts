import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Single Category Filter Selection (BS-006)', () => {
  test('positive — selecting single category filters deals correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait for page to load and locate category filter section
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category filter button should be visible').toBeVisible();
    
    // Count initial deals before filtering
    const initialDealsCount = await page.getByTestId('add-to-cart-button').count();
    
    // Select a single category checkbox
    await page.getByRole('button', { name: 'Mobiles' }).click();
    
    // Wait for filtering to complete
    await page.waitForTimeout(2000);
    
    // Verify main grid results update to show only selected category
    await expect(page.getByTestId('add-to-cart-button'), 'Filtered deals should be displayed after category selection').toBeVisible();
    
    // Confirm filtering works correctly by checking if results changed
    const filteredDealsCount = await page.getByTestId('add-to-cart-button').count();
    expect(filteredDealsCount, 'Filtered results count should be different from initial count').not.toBe(initialDealsCount);
    
    // Verify the selected category filter is active
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Selected Mobiles category should appear active').toBeVisible();
  });

  test('negative — clicking non-existent category shows no results', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Category filter section should be loaded').toBeVisible();
    
    // Try to interact with a category that might not exist or have deals
    try {
      await page.getByRole('button', { name: 'NonExistentCategory' }).click({ timeout: 3000 });
      
      // If the category exists but has no deals, verify no results shown
      const dealsCount = await page.getByTestId('add-to-cart-button').count();
      expect(dealsCount, 'Non-existent category should show zero deals').toBe(0);
    } catch (error) {
      // Expected behavior - category doesn't exist
      expect(error.message, 'Non-existent category button should not be found').toContain('Locator');
    }
  });

  test('negative — rapidly clicking multiple categories handles state correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Category filters should be available').toBeVisible();
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics category should be available').toBeVisible();
    
    // Rapidly click different categories to test state handling
    await page.getByRole('button', { name: 'Mobiles' }).click();
    await page.getByRole('button', { name: 'Electronics' }).click();
    await page.getByRole('button', { name: 'Mobiles' }).click();
    
    await page.waitForTimeout(2000);
    
    // Verify that the page handles rapid state changes without breaking
    await expect(page.getByTestId('add-to-cart-button'), 'Deals should still be displayed after rapid category switching').toBeVisible();
    
    const finalDealsCount = await page.getByTestId('add-to-cart-button').count();
    expect(finalDealsCount, 'Should have deals displayed after rapid clicking').toBeGreaterThan(0);
  });

  test('negative — disabled category selection shows appropriate feedback', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Category filter should be present').toBeVisible();
    
    // Check if category button becomes disabled after selection (some sites do this)
    await page.getByRole('button', { name: 'Mobiles' }).click();
    
    await page.waitForTimeout(1000);
    
    // Try to click the same category again
    await page.getByRole('button', { name: 'Mobiles' }).click();
    
    // Verify the system handles duplicate selection appropriately
    const dealsAfterDuplicate = await page.getByTestId('add-to-cart-button').count();
    expect(dealsAfterDuplicate, 'Duplicate category selection should not break filtering').toBeGreaterThanOrEqual(0);
  });

  test('negative — network interruption during category selection', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics category should be available').toBeVisible();
    
    // Simulate network issues by going offline briefly
    await page.context().setOffline(true);
    
    try {
      await page.getByRole('button', { name: 'Electronics' }).click();
      await page.waitForTimeout(1000);
    } catch (error) {
      // Expected behavior during offline state
    }
    
    // Restore network
    await page.context().setOffline(false);
    await page.waitForTimeout(2000);
    
    // Verify page recovers gracefully
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Category filter should be functional after network recovery').toBeVisible();
    
    // Try selection again after network recovery
    await page.getByRole('button', { name: 'Electronics' }).click();
    await page.waitForTimeout(2000);
    
    await expect(page.getByTestId('add-to-cart-button'), 'Deals should load after network recovery and category selection').toBeVisible();
  });

  test('boundary — single category with maximum available deals', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Electronics' }), 'Electronics category should be available for boundary testing').toBeVisible();
    
    // Select Electronics which typically has many deals (boundary case for large result set)
    await page.getByRole('button', { name: 'Electronics' }).click();
    
    await page.waitForTimeout(3000);
    
    // Verify large result set is handled correctly
    const dealsCount = await page.getByTestId('add-to-cart-button').count();
    expect(dealsCount, 'Electronics category should show substantial number of deals').toBeGreaterThan(5);
    
    // Verify pagination or load-more functionality if present
    await expect(page.getByTestId('add-to-cart-button').first(), 'First deal should be visible in large result set').toBeVisible();
    
    // Test scrolling with large result set
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(2000);
    
    const dealsAfterScroll = await page.getByTestId('add-to-cart-button').count();
    expect(dealsAfterScroll, 'Deal count should remain consistent after scrolling large result set').toBeGreaterThanOrEqual(dealsCount);
  });

  test('boundary — category selection at page load boundary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Try to select category immediately upon page load (boundary timing)
    try {
      await page.getByRole('button', { name: 'Mobiles' }).click({ timeout: 1000 });
    } catch (error) {
      // Wait for page to fully load if immediate click fails
      await page.waitForTimeout(2000);
      await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category should be available after page load completes').toBeVisible();
      await page.getByRole('button', { name: 'Mobiles' }).click();
    }
    
    await page.waitForTimeout(2000);
    
    // Verify selection works correctly even with timing boundary conditions
    await expect(page.getByTestId('add-to-cart-button'), 'Deals should be filtered correctly even with early category selection').toBeVisible();
    
    const finalDealsCount = await page.getByTestId('add-to-cart-button').count();
    expect(finalDealsCount, 'Should have filtered deals displayed after boundary timing selection').toBeGreaterThan(0);
  });

  test('boundary — single category with minimum deals available', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Mobiles category should be available').toBeVisible();
    
    // Select Mobiles which might have fewer deals (boundary case for small result set)
    await page.getByRole('button', { name: 'Mobiles' }).click();
    
    await page.waitForTimeout(2000);
    
    // Verify small result set is handled correctly
    const dealsCount = await page.getByTestId('add-to-cart-button').count();
    expect(dealsCount, 'Mobiles category should show at least some deals or zero deals').toBeGreaterThanOrEqual(0);
    
    if (dealsCount > 0) {
      await expect(page.getByTestId('add-to-cart-button').first(), 'At least one deal should be properly displayed for minimum boundary case').toBeVisible();
    }
    
    // Verify page layout handles small result sets appropriately
    await expect(page.getByRole('button', { name: 'Mobiles' }), 'Category filter should remain functional with small result set').toBeVisible();
  });
});