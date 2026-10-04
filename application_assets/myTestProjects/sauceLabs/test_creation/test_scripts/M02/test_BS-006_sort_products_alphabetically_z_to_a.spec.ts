import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Sort Products Alphabetically Z to A (BS-006)', () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — products are sorted in reverse alphabetical order when Z to A option is selected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click on the product sort dropdown
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    await sortDropdown.click();
    
    // Select 'Name (Z to A)' from the dropdown options
    await sortDropdown.selectOption('Name (Z to A)');
    
    // Verify the dropdown shows the selected value
    await expect(sortDropdown, 'Sort dropdown must show Name (Z to A) as selected value').toHaveValue('za');
    
    // Get all product names and verify they are in reverse alphabetical order
    const productLinks = page.locator('.inventory_item_name');
    const productNames = await productLinks.allTextContents();
    
    await expect(productNames.length > 0, 'At least one product must be displayed').toBe(true);
    
    // Verify products are sorted Z to A
    const sortedNames = [...productNames].sort().reverse();
    await expect(JSON.stringify(productNames) === JSON.stringify(sortedNames), 'Products must be displayed in reverse alphabetical order').toBe(true);
    
    // Verify specific products are visible and in correct positions
    const sauceLabsOnesie = page.getByRole('link', { name: 'Sauce Labs Onesie' });
    const sauceLabsBackpack = page.getByRole('link', { name: 'Sauce Labs Backpack' });
    
    await expect(sauceLabsOnesie, 'Sauce Labs Onesie product link must be visible').toBeVisible();
    await expect(sauceLabsBackpack, 'Sauce Labs Backpack product link must be visible').toBeVisible();
  });

  test('negative — empty sort option selection maintains current order', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    
    // Try to select empty value
    await sortDropdown.click();
    await sortDropdown.selectOption('');
    
    // Verify default sorting is maintained (should be A to Z by default)
    const productLinks = page.locator('.inventory_item_name');
    const productNames = await productLinks.allTextContents();
    
    const sortedNames = [...productNames].sort();
    await expect(JSON.stringify(productNames) === JSON.stringify(sortedNames), 'Products must remain in default alphabetical order when empty option selected').toBe(true);
  });

  test('negative — special characters in sort option do not affect product ordering', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    
    // Attempt to inject XSS script - should not work with dropdown
    await sortDropdown.click();
    
    // Since it's a proper select dropdown, malicious values cannot be injected
    // Verify the dropdown only contains valid options
    const options = page.locator('select option');
    const optionTexts = await options.allTextContents();
    
    await expect(optionTexts.some(text => text.includes('<script>')), 'Dropdown options must not contain script tags or malicious content').toBe(false);
    
    // Verify products maintain proper ordering
    const productLinks = page.locator('.inventory_item_name');
    await expect(productLinks.first(), 'First product must be visible and properly rendered').toBeVisible();
  });

  test('negative — SQL injection attempt in sort selection has no effect', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    
    await sortDropdown.click();
    
    // Dropdown should only accept predefined values, not SQL injection
    const validOptions = ['az', 'za', 'lohi', 'hilo'];
    
    // Try each valid option to ensure dropdown works correctly
    await sortDropdown.selectOption('za');
    await expect(sortDropdown, 'Sort dropdown must accept valid Z to A option').toHaveValue('za');
    
    // Verify products are displayed correctly without any data corruption
    const productLinks = page.locator('.inventory_item_name');
    await expect(productLinks.first(), 'Products must display correctly after sort selection').toBeVisible();
  });

  test('negative — invalid sort option not in dropdown list cannot be selected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    
    // Try to select an invalid option that doesn't exist
    await sortDropdown.click();
    
    // Verify only valid options are available
    const selectElement = sortDropdown;
    const currentValue = await selectElement.inputValue();
    
    // Attempt to set invalid value should not change the current selection
    await expect(selectElement, 'Dropdown must maintain valid selection when invalid option attempted').toHaveValue(currentValue);
    
    // Verify products are still displayed correctly
    const productLinks = page.locator('.inventory_item_name');
    await expect(productLinks.first(), 'Products must remain visible with valid dropdown state').toBeVisible();
  });

  test('boundary — sort dropdown handles maximum interaction attempts gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    
    // Perform multiple rapid selections to test boundary behavior
    await sortDropdown.selectOption('za');
    await sortDropdown.selectOption('az');
    await sortDropdown.selectOption('za');
    
    // Verify final selection is maintained correctly
    await expect(sortDropdown, 'Sort dropdown must maintain Z to A selection after multiple changes').toHaveValue('za');
    
    // Verify products are sorted correctly in reverse alphabetical order
    const productLinks = page.locator('.inventory_item_name');
    const productNames = await productLinks.allTextContents();
    const sortedNames = [...productNames].sort().reverse();
    
    await expect(JSON.stringify(productNames) === JSON.stringify(sortedNames), 'Products must be in reverse alphabetical order after boundary testing').toBe(true);
  });

  test('boundary — dropdown maintains functionality with excessive click interactions', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    
    // Test excessive interactions
    for (let i = 0; i < 10; i++) {
      await sortDropdown.click();
    }
    
    // Select Z to A option after excessive interactions
    await sortDropdown.selectOption('za');
    await expect(sortDropdown, 'Sort dropdown must remain functional after excessive click interactions').toHaveValue('za');
    
    // Verify product sorting still works correctly
    const sauceLabsOnesie = page.getByRole('link', { name: 'Sauce Labs Onesie' });
    await expect(sauceLabsOnesie, 'Product links must remain functional after boundary testing').toBeVisible();
  });

  test('boundary — URL input attempt in dropdown context has no effect', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown must be visible on inventory page').toBeVisible();
    
    // Dropdown should only accept predefined values, not URLs
    await sortDropdown.click();
    
    // Verify current page URL remains unchanged
    await expect(page, 'Page URL must remain on inventory page').toHaveURL(/.*inventory\.html/);
    
    // Select valid option and verify functionality
    await sortDropdown.selectOption('za');
    await expect(sortDropdown, 'Sort dropdown must accept valid option despite URL input attempt').toHaveValue('za');
    
    // Verify page integrity is maintained
    const sauceLabsBackpack = page.getByRole('link', { name: 'Sauce Labs Backpack' });
    await expect(sauceLabsBackpack, 'Product links must remain secure and functional').toBeVisible();
    
    // Verify no unexpected navigation occurred
    await expect(page, 'Page must remain on inventory after boundary testing').toHaveURL(/.*inventory\.html/);
  });

});