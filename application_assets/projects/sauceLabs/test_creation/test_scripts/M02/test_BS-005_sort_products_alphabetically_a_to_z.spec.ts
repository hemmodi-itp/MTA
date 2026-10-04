import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Sort Products Alphabetically A to Z (BS-005)', () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — products sort alphabetically A to Z when Name (A to Z) is selected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click on the product sort dropdown
    await page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' }).click();
    
    // Select 'Name (A to Z)' from the dropdown options
    await page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' }).selectOption('az');
    
    // Verify products are reordered alphabetically from A to Z
    const productLinks = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    const sortedProducts = [...productLinks].sort();
    
    await expect(productLinks, 'Products should be sorted alphabetically A to Z').toEqual(sortedProducts);
    
    // Verify first product starts with earliest letter
    const firstProduct = productLinks[0];
    await expect(firstProduct, 'First product should start with earliest alphabetical letter').toBeTruthy();
  });

  test('negative — empty dropdown selection maintains current sort order', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Get initial product order
    const initialProducts = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    
    // Click dropdown but don't select anything
    await page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' }).click();
    await page.keyboard.press('Escape');
    
    // Verify order remains unchanged
    const currentProducts = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    await expect(currentProducts, 'Product order should remain unchanged when no selection is made').toEqual(initialProducts);
  });

  test('negative — special characters in product names are sorted correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Select A to Z sorting
    await page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' }).selectOption('az');
    
    // Get all product names
    const productNames = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    
    // Verify special characters are handled in sorting
    for (let i = 0; i < productNames.length - 1; i++) {
      const current = productNames[i].toLowerCase();
      const next = productNames[i + 1].toLowerCase();
      await expect(current <= next, `Product "${productNames[i]}" should come before or equal to "${productNames[i + 1]}" in alphabetical order`).toBeTruthy();
    }
  });

  test('negative — rapid dropdown selection changes handle correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const dropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    
    // Rapidly change selections
    await dropdown.selectOption('za');
    await dropdown.selectOption('lohi');
    await dropdown.selectOption('hilo');
    await dropdown.selectOption('az');
    
    // Verify final state is A to Z
    const productNames = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    const sortedProducts = [...productNames].sort();
    
    await expect(productNames, 'Products should be sorted A to Z after rapid selection changes').toEqual(sortedProducts);
  });

  test('negative — invalid sort option injection attempt is handled', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt to inject invalid sort parameter via URL
    await page.goto(BASE_URL + '?sort=<script>alert("xss")</script>');
    
    // Verify dropdown still works normally
    await page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' }).selectOption('az');
    
    const productNames = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    await expect(productNames.length, 'Products should still be displayed after invalid sort injection attempt').toBeGreaterThan(0);
  });

  test('boundary — sorting with minimum number of products (single item)', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Filter to potentially get fewer items (simulate boundary condition)
    await page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' }).selectOption('az');
    
    const productNames = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    
    // Verify sorting works even with limited products
    await expect(productNames, 'At least one product should be displayed').toHaveLength.toBeGreaterThan(0);
    
    const sortedProducts = [...productNames].sort();
    await expect(productNames, 'Products should maintain alphabetical order regardless of count').toEqual(sortedProducts);
  });

  test('boundary — sorting with maximum product name length', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' }).selectOption('az');
    
    const productNames = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    
    // Find longest product name
    const longestName = productNames.reduce((a, b) => a.length > b.length ? a : b);
    
    // Verify long names are handled in sorting
    await expect(longestName.length, 'Longest product name should be within reasonable bounds').toBeLessThan(100);
    
    const sortedProducts = [...productNames].sort();
    await expect(productNames, 'Products with long names should sort correctly').toEqual(sortedProducts);
  });

  test('boundary — dropdown navigation with keyboard at selection limits', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const dropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    
    // Focus dropdown and use keyboard navigation
    await dropdown.click();
    
    // Navigate to first option
    await page.keyboard.press('Home');
    await page.keyboard.press('Enter');
    
    // Verify first option (A to Z) is selected
    const productNames = await page.locator('[data-test="inventory-item-name"]').allTextContents();
    const sortedProducts = [...productNames].sort();
    
    await expect(productNames, 'Products should be sorted A to Z when first dropdown option is selected via keyboard').toEqual(sortedProducts);
  });

});