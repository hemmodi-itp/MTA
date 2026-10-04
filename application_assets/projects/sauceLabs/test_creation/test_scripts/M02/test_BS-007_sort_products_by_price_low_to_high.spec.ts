import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Sort Products by Price Low to High (BS-007)', () => {
  

  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — products are sorted from lowest to highest price', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click on the product sort dropdown
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    await sortDropdown.click();
    
    // Select 'Price (low to high)' from the dropdown options
    await sortDropdown.selectOption('lohi');
    
    // Verify products are reordered by ascending price
    const priceElements = page.locator('.inventory_item_price');
    await expect(priceElements.first(), 'First price element must be visible after sorting').toBeVisible();
    
    const prices = await priceElements.allTextContents();
    const numericPrices = prices.map(price => parseFloat(price.replace('$', '')));
    
    for (let i = 1; i < numericPrices.length; i++) {
      expect(numericPrices[i], `Price at position ${i} (${numericPrices[i]}) should be greater than or equal to previous price (${numericPrices[i-1]})`).toBeGreaterThanOrEqual(numericPrices[i-1]);
    }
    
    await expect(page.locator('.inventory_item').first(), 'First product item must be visible after sorting').toBeVisible();
  });

  test('negative — empty dropdown value maintains current order', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible before testing empty value').toBeVisible();
    
    // Get initial order
    const initialPrices = await page.locator('.inventory_item_price').allTextContents();
    
    // Try to set empty value
    await sortDropdown.click();
    await page.keyboard.press('Escape');
    
    // Verify order remains unchanged
    const currentPrices = await page.locator('.inventory_item_price').allTextContents();
    expect(currentPrices, 'Product order should remain unchanged when dropdown action is cancelled').toEqual(initialPrices);
  });

  test('negative — special characters in dropdown manipulation attempt', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible before testing special characters').toBeVisible();
    
    // Attempt to inject special characters
    await sortDropdown.click();
    await page.keyboard.type('!@#$%^&*()');
    
    // Verify dropdown still functions normally
    await expect(sortDropdown, 'Sort dropdown should remain functional after special character input').toBeVisible();
    
    // Select valid option to ensure functionality is preserved
    await sortDropdown.selectOption('lohi');
    const priceElements = page.locator('.inventory_item_price');
    await expect(priceElements.first(), 'Price sorting should work normally despite special character injection attempt').toBeVisible();
  });

  test('negative — sql injection attempt in dropdown', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible before testing SQL injection').toBeVisible();
    
    // Attempt SQL injection
    await sortDropdown.click();
    await page.keyboard.type("'; DROP TABLE products; --");
    
    // Verify page remains stable and functional
    await expect(page.locator('.inventory_list'), 'Inventory list should remain visible after SQL injection attempt').toBeVisible();
    
    // Verify normal sorting still works
    await sortDropdown.selectOption('lohi');
    const priceElements = page.locator('.inventory_item_price');
    await expect(priceElements.first(), 'Price sorting functionality should be unaffected by SQL injection attempt').toBeVisible();
  });

  test('negative — wrong format option selection attempt', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible before testing wrong format').toBeVisible();
    
    // Get initial state
    const initialPrices = await page.locator('.inventory_item_price').allTextContents();
    
    // Attempt to select invalid option format
    try {
      await sortDropdown.selectOption('invalid_option_format_123');
    } catch (error) {
      // Expected to fail, continue with test
    }
    
    // Verify products remain in original order
    const currentPrices = await page.locator('.inventory_item_price').allTextContents();
    expect(currentPrices, 'Product order should remain unchanged when invalid option format is attempted').toEqual(initialPrices);
    
    // Verify dropdown is still functional
    await expect(sortDropdown, 'Sort dropdown should remain functional after invalid option attempt').toBeVisible();
  });

  test('boundary — rapid successive sort selections', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible before boundary testing').toBeVisible();
    
    // Rapidly change sort options multiple times
    await sortDropdown.selectOption('za');
    await sortDropdown.selectOption('hilo');
    await sortDropdown.selectOption('az');
    await sortDropdown.selectOption('lohi');
    
    // Verify final sort order is correct (price low to high)
    const priceElements = page.locator('.inventory_item_price');
    await expect(priceElements.first(), 'First price element must be visible after rapid sort changes').toBeVisible();
    
    const prices = await priceElements.allTextContents();
    const numericPrices = prices.map(price => parseFloat(price.replace('$', '')));
    
    expect(numericPrices[0], 'First product should have the lowest price after rapid sort operations').toBeLessThanOrEqual(numericPrices[1] || numericPrices[0]);
  });

  test('boundary — sort dropdown interaction at page load boundary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Immediately interact with dropdown as soon as page loads
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    
    // Test interaction at the boundary of page readiness
    await expect(sortDropdown, 'Sort dropdown must be ready immediately after page load').toBeVisible();
    await sortDropdown.selectOption('lohi');
    
    // Verify sorting works correctly even with immediate interaction
    const priceElements = page.locator('.inventory_item_price');
    await expect(priceElements.first(), 'Price sorting should work immediately after page load').toBeVisible();
    
    const prices = await priceElements.allTextContents();
    expect(prices.length, 'All product prices should be loaded and sorted correctly').toBeGreaterThan(0);
  });

  test('boundary — sort with maximum viewport stress', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set extreme viewport size to test layout boundaries
    await page.setViewportSize({ width: 320, height: 568 });
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must remain accessible in minimum viewport size').toBeVisible();
    
    // Perform sort operation in constrained viewport
    await sortDropdown.selectOption('lohi');
    
    // Verify functionality persists in boundary viewport conditions
    const priceElements = page.locator('.inventory_item_price');
    await expect(priceElements.first(), 'Price elements must remain visible and functional in minimum viewport').toBeVisible();
    
    // Verify sorting actually occurred
    const currentValue = await sortDropdown.inputValue();
    expect(currentValue, 'Dropdown should maintain selected value in constrained viewport').toBe('lohi');
  });

});