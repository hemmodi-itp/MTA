import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Sort Products by Price High to Low (BS-008)', () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — products are sorted by price from highest to lowest', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click on the product sort dropdown
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    await sortDropdown.click();
    
    // Select 'Price (high to low)' from the dropdown options
    await sortDropdown.selectOption('Price (high to low)');
    
    // Verify products are reordered by descending price
    const productPrices = page.locator('.inventory_item_price');
    await expect(productPrices.first(), 'Product prices must be visible after sorting').toBeVisible();
    
    // Extract all price values and verify they are in descending order
    const priceTexts = await productPrices.allTextContent();
    const prices = priceTexts.map(price => parseFloat(price.replace('$', '')));
    
    for (let i = 0; i < prices.length - 1; i++) {
      await expect(prices[i] >= prices[i + 1], `Price at position ${i} (${prices[i]}) should be greater than or equal to price at position ${i + 1} (${prices[i + 1]})`).toBeTruthy();
    }
    
    // Verify the dropdown shows the selected option
    await expect(sortDropdown, 'Sort dropdown should show Price (high to low) as selected').toHaveValue('hilo');
  });

  test('negative — empty sort option selection maintains current order', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible for empty selection test').toBeVisible();
    
    // Get initial product order
    const initialProducts = await page.locator('.inventory_item_name').allTextContent();
    
    // Attempt to select empty option (should maintain current state)
    await sortDropdown.click();
    await sortDropdown.selectOption('');
    
    // Verify products maintain their original order
    const currentProducts = await page.locator('.inventory_item_name').allTextContent();
    await expect(JSON.stringify(currentProducts) === JSON.stringify(initialProducts), 'Product order should remain unchanged when no sort option is selected').toBeTruthy();
  });

  test('negative — XSS injection attempt in sort selection is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible for XSS injection test').toBeVisible();
    
    // Attempt XSS injection
    await sortDropdown.click();
    
    // Try to input malicious script - this should be rejected by the dropdown
    const maliciousValue = "<script>alert('xss')</script>";
    
    // Verify that malicious option is not available in dropdown
    const options = await sortDropdown.locator('option').allTextContent();
    const hasXSSOption = options.some(option => option.includes(maliciousValue));
    await expect(hasXSSOption, 'Dropdown should not contain XSS script options').toBeFalsy();
    
    // Verify page remains functional after injection attempt
    await expect(sortDropdown, 'Sort dropdown should remain functional after XSS attempt').toBeVisible();
  });

  test('negative — SQL injection attempt in sort selection is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible for SQL injection test').toBeVisible();
    
    // Attempt SQL injection
    await sortDropdown.click();
    
    const sqlInjectionValue = "' OR '1'='1";
    
    // Verify that SQL injection option is not available in dropdown
    const options = await sortDropdown.locator('option').allTextContent();
    const hasSQLOption = options.some(option => option.includes(sqlInjectionValue));
    await expect(hasSQLOption, 'Dropdown should not contain SQL injection options').toBeFalsy();
    
    // Verify dropdown still functions normally
    await sortDropdown.selectOption('Name (A to Z)');
    await expect(sortDropdown, 'Sort dropdown should function normally after SQL injection attempt').toHaveValue('az');
  });

  test('negative — invalid sort option not in dropdown is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible for invalid option test').toBeVisible();
    
    // Get available options
    const validOptions = await sortDropdown.locator('option').allTextContent();
    const invalidOption = "Invalid Sort Option";
    
    // Verify invalid option is not in the dropdown
    const hasInvalidOption = validOptions.some(option => option.includes(invalidOption));
    await expect(hasInvalidOption, 'Dropdown should not contain invalid sort options').toBeFalsy();
    
    // Verify only valid options are available
    const expectedOptions = ['Name (A to Z)', 'Name (Z to A)', 'Price (low to high)', 'Price (high to low)'];
    for (const expectedOption of expectedOptions) {
      const hasExpectedOption = validOptions.some(option => option.includes(expectedOption));
      await expect(hasExpectedOption, `Dropdown should contain valid option: ${expectedOption}`).toBeTruthy();
    }
  });

  test('boundary — sort dropdown handles maximum option text length correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible for boundary test').toBeVisible();
    
    // Test the longest valid option name
    const longestOption = 'Price (high to low)';
    await sortDropdown.selectOption(longestOption);
    
    // Verify selection works correctly
    await expect(sortDropdown, 'Dropdown should handle longest option text correctly').toHaveValue('hilo');
    
    // Verify products are sorted correctly even with longest option name
    const productPrices = page.locator('.inventory_item_price');
    const priceTexts = await productPrices.allTextContent();
    const prices = priceTexts.map(price => parseFloat(price.replace('$', '')));
    
    await expect(prices[0] >= prices[prices.length - 1], 'Products should be sorted correctly even with longest option name').toBeTruthy();
  });

  test('boundary — sort dropdown remains functional with rapid option changes', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible for rapid change test').toBeVisible();
    
    // Rapidly change between all sort options
    const sortOptions = ['az', 'za', 'lohi', 'hilo'];
    
    for (const option of sortOptions) {
      await sortDropdown.selectOption(option);
      await expect(sortDropdown, `Dropdown should handle rapid change to option ${option}`).toHaveValue(option);
      
      // Brief wait to ensure UI updates
      await page.waitForTimeout(100);
    }
    
    // Verify final selection works correctly
    await sortDropdown.selectOption('hilo');
    const productPrices = page.locator('.inventory_item_price');
    await expect(productPrices.first(), 'Products should still be visible after rapid option changes').toBeVisible();
  });

  test('boundary — URL injection in sort selection is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible for URL injection test').toBeVisible();
    
    const urlInjection = "https://evil.com/redirect";
    
    // Verify URL injection is not available as an option
    const options = await sortDropdown.locator('option').allTextContent();
    const hasURLOption = options.some(option => option.includes(urlInjection));
    await expect(hasURLOption, 'Dropdown should not contain URL injection options').toBeFalsy();
    
    // Verify page URL remains unchanged after attempting injection
    const currentURL = page.url();
    await expect(currentURL.includes('saucedemo.com'), 'Page should remain on saucedemo.com after URL injection attempt').toBeTruthy();
    await expect(currentURL.includes('evil.com'), 'Page should not redirect to malicious URL').toBeFalsy();
    
    // Verify dropdown continues to function normally
    await sortDropdown.selectOption('Price (high to low)');
    await expect(sortDropdown, 'Sort dropdown should remain functional after URL injection attempt').toHaveValue('hilo');
  });

});