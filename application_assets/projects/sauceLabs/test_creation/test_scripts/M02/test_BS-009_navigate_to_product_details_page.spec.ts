import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Navigate to Product Details Page (BS-009)', () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — clicking product image successfully navigates to product details page', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click on the first product image link
    await page.getByTestId('item-0-img-link').click();
    
    // Verify navigation to product details page by checking URL contains inventory-item
    await expect(page, 'Page should navigate to product details URL').toHaveURL(/.*inventory-item\.html.*/);
    
    // Verify product details page loads with product information
    await expect(page.locator('.inventory_details'), 'Product details section should be visible').toBeVisible();
    
    // Verify product name is displayed
    await expect(page.locator('.inventory_details_name'), 'Product name should be displayed on details page').toBeVisible();
    
    // Verify product description is displayed
    await expect(page.locator('.inventory_details_desc'), 'Product description should be displayed on details page').toBeVisible();
    
    // Verify product price is displayed
    await expect(page.locator('.inventory_details_price'), 'Product price should be displayed on details page').toBeVisible();
  });

  test('positive — clicking product title link successfully navigates to product details page', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click on the product title link
    await page.getByRole('link', { name: 'Sauce Labs Backpack' }).click();
    
    // Verify navigation to product details page
    await expect(page, 'Page should navigate to product details URL when clicking title').toHaveURL(/.*inventory-item\.html.*/);
    
    // Verify product details content is displayed
    await expect(page.locator('.inventory_details'), 'Product details section should be visible after clicking title').toBeVisible();
  });

  test('negative — attempting to navigate with empty product data fails gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to a malformed product URL directly
    await page.goto(BASE_URL.replace('inventory.html', 'inventory-item.html?id='));
    
    // Verify error handling or redirect back to inventory
    const currentUrl = page.url();
    const hasError = await page.locator('.error-message').isVisible().catch(() => false);
    const backOnInventory = currentUrl.includes('inventory.html');
    
    await expect(hasError || backOnInventory, 'Empty product ID should show error or redirect to inventory').toBeTruthy();
  });

  test('negative — navigating with special characters in product ID fails gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt navigation with special characters in product ID
    await page.goto(BASE_URL.replace('inventory.html', 'inventory-item.html?id=<script>alert("xss")</script>'));
    
    // Verify system handles special characters safely
    const pageContent = await page.content();
    await expect(pageContent.includes('<script>'), 'Special characters should not be executed as code').toBeFalsy();
    
    // Should show error or redirect
    const hasError = await page.locator('.error-message').isVisible().catch(() => false);
    const backOnInventory = page.url().includes('inventory.html');
    
    await expect(hasError || backOnInventory, 'Special characters in product ID should be handled safely').toBeTruthy();
  });

  test('negative — SQL injection attempt in product ID parameter fails gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt SQL injection in product ID
    await page.goto(BASE_URL.replace('inventory.html', 'inventory-item.html?id=1\' OR \'1\'=\'1'));
    
    // Verify SQL injection is prevented
    const pageTitle = await page.title();
    const hasError = await page.locator('.error-message').isVisible().catch(() => false);
    const backOnInventory = page.url().includes('inventory.html');
    
    await expect(hasError || backOnInventory, 'SQL injection attempt should be blocked and handled safely').toBeTruthy();
  });

  test('negative — invalid product ID format shows appropriate error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate with invalid product ID format
    await page.goto(BASE_URL.replace('inventory.html', 'inventory-item.html?id=invalid_format_999'));
    
    // Verify invalid format is handled properly
    const hasError = await page.locator('.error-message').isVisible().catch(() => false);
    const backOnInventory = page.url().includes('inventory.html');
    const hasProductDetails = await page.locator('.inventory_details').isVisible().catch(() => false);
    
    await expect(hasProductDetails, 'Invalid product ID should not show product details').toBeFalsy();
    await expect(hasError || backOnInventory, 'Invalid product ID format should show error or redirect').toBeTruthy();
  });

  test('boundary — navigating to product at boundary ID value works correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // First click a valid product to establish baseline
    await page.getByTestId('item-1-img-link').click();
    
    // Verify navigation works for boundary case
    await expect(page, 'Navigation to boundary product ID should work').toHaveURL(/.*inventory-item\.html.*/);
    
    // Verify product details are displayed for boundary case
    await expect(page.locator('.inventory_details'), 'Product details should be visible for boundary ID').toBeVisible();
    
    // Verify essential product information is present
    await expect(page.locator('.inventory_details_name'), 'Product name should be displayed for boundary ID').toBeVisible();
  });

  test('boundary — extremely long product ID parameter is handled appropriately', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Create very long product ID (over 1000 characters)
    const longId = 'a'.repeat(1001);
    await page.goto(BASE_URL.replace('inventory.html', `inventory-item.html?id=${longId}`));
    
    // Verify system handles long input gracefully
    const hasError = await page.locator('.error-message').isVisible().catch(() => false);
    const backOnInventory = page.url().includes('inventory.html');
    
    await expect(hasError || backOnInventory, 'Extremely long product ID should be rejected or cause redirect').toBeTruthy();
  });

  test('boundary — URL manipulation with valid product navigation still works', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Click product first to get valid URL format
    await page.getByTestId('item-0-img-link').click();
    
    // Verify we're on a product details page
    await expect(page, 'Should be on product details page after URL navigation').toHaveURL(/.*inventory-item\.html.*/);
    
    // Verify all product detail elements are present at boundary
    await expect(page.locator('.inventory_details'), 'Product details container should be visible').toBeVisible();
    await expect(page.locator('.inventory_details_name'), 'Product name should be visible in boundary test').toBeVisible();
    await expect(page.locator('.inventory_details_price'), 'Product price should be visible in boundary test').toBeVisible();
    await expect(page.locator('.inventory_details_desc'), 'Product description should be visible in boundary test').toBeVisible();
  });

});