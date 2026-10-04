import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Maintain Cart State After Page Refresh (BS-014)', () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — cart state persists after browser refresh', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add multiple items to cart
    const addToCartButtons = page.getByRole('button', { name: 'Add to cart' });
    await addToCartButtons.first().click();
    await addToCartButtons.nth(1).click();
    await addToCartButtons.nth(2).click();
    
    // Note the cart badge count before refresh
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart badge should show count of 3 items').toHaveText('3');
    
    // Get the current state of buttons (should show "Remove" text)
    const firstRemoveButton = page.getByRole('button', { name: 'Remove' }).first();
    await expect(firstRemoveButton, 'First product should show Remove button before refresh').toBeVisible();
    
    // Refresh the browser page
    await page.reload();
    
    // Verify cart badge count is maintained
    await expect(cartBadge, 'Cart badge should still show count of 3 items after refresh').toHaveText('3');
    
    // Verify product selection states are maintained (Remove buttons still visible)
    const removeButtons = page.getByRole('button', { name: 'Remove' });
    await expect(removeButtons, 'All Remove buttons should be visible after refresh').toHaveCount(3);
    
    // Verify Add to cart buttons are reduced (only 3 should remain)
    const remainingAddButtons = page.getByRole('button', { name: 'Add to cart' });
    await expect(remainingAddButtons, 'Remaining Add to cart buttons should be 3 after refresh').toHaveCount(3);
  });

  test('negative — cart state with malformed localStorage manipulation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart normally
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    // Manipulate localStorage with invalid JSON
    await page.evaluate(() => {
      localStorage.setItem('cart-contents', 'invalid-json-string');
    });
    
    // Refresh page
    await page.reload();
    
    // Verify system handles corrupted cart data gracefully
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart badge should not be visible with corrupted data').not.toBeVisible();
    
    // Verify all buttons reset to Add to cart state
    const addToCartButtons = page.getByRole('button', { name: 'Add to cart' });
    await expect(addToCartButtons, 'All buttons should be Add to cart after cart corruption').toHaveCount(6);
  });

  test('negative — cart state with SQL injection in localStorage', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    // Inject SQL-like payload into localStorage
    await page.evaluate(() => {
      localStorage.setItem('cart-contents', "'; DROP TABLE cart; --");
    });
    
    // Refresh page
    await page.reload();
    
    // Verify application handles malicious input safely
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart badge should not show malicious content').not.toBeVisible();
    
    // Verify page loads normally without SQL injection effects
    const inventoryContainer = page.locator('.inventory_container');
    await expect(inventoryContainer, 'Inventory container should load normally despite injection attempt').toBeVisible();
  });

  test('negative — cart state with XSS script in localStorage', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    // Insert XSS payload into localStorage
    await page.evaluate(() => {
      localStorage.setItem('cart-contents', '<script>alert("xss")</script>');
    });
    
    // Refresh page
    await page.reload();
    
    // Verify no script execution and safe handling
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart badge should not execute script content').not.toBeVisible();
    
    // Verify page functionality remains intact
    const addToCartButtons = page.getByRole('button', { name: 'Add to cart' });
    await expect(addToCartButtons, 'Add to cart buttons should be functional after XSS attempt').toHaveCount(6);
  });

  test('negative — empty cart state after localStorage clearing', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add items to cart
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    // Clear localStorage completely
    await page.evaluate(() => {
      localStorage.clear();
    });
    
    // Refresh page
    await page.reload();
    
    // Verify cart resets to empty state
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart badge should not be visible with cleared localStorage').not.toBeVisible();
    
    // Verify all buttons reset to Add to cart
    const addToCartButtons = page.getByRole('button', { name: 'Add to cart' });
    await expect(addToCartButtons, 'All buttons should reset to Add to cart state').toHaveCount(6);
  });

  test('boundary — maximum cart items before refresh', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add all available items to cart (boundary test - maximum items)
    const addToCartButtons = page.getByRole('button', { name: 'Add to cart' });
    const buttonCount = await addToCartButtons.count();
    
    for (let i = 0; i < buttonCount; i++) {
      await addToCartButtons.nth(i).click();
    }
    
    // Verify maximum cart count
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart badge should show maximum item count before refresh').toHaveText(buttonCount.toString());
    
    // Refresh page
    await page.reload();
    
    // Verify all items persist after refresh
    await expect(cartBadge, 'Cart badge should maintain maximum count after refresh').toHaveText(buttonCount.toString());
    
    // Verify all buttons show Remove state
    const removeButtons = page.getByRole('button', { name: 'Remove' });
    await expect(removeButtons, 'All buttons should show Remove state after refresh').toHaveCount(buttonCount);
  });

  test('boundary — cart state with extremely long localStorage data', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    // Create extremely long string (boundary test)
    const longString = 'x'.repeat(1000000); // 1MB string
    await page.evaluate((data) => {
      localStorage.setItem('extra-data', data);
    }, longString);
    
    // Refresh page
    await page.reload();
    
    // Verify cart still functions with large localStorage
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart should function normally despite large localStorage data').toHaveText('1');
    
    // Verify page loads without performance issues
    const removeButton = page.getByRole('button', { name: 'Remove' });
    await expect(removeButton, 'Remove button should be visible despite localStorage size').toBeVisible();
  });

  test('boundary — rapid refresh cycles maintain cart state', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add items to cart
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    const cartBadge = page.getByTestId('shopping-cart-link').locator('.shopping_cart_badge');
    await expect(cartBadge, 'Cart badge should show initial count').toHaveText('1');
    
    // Perform rapid refresh cycles (boundary test)
    for (let i = 0; i < 5; i++) {
      await page.reload();
      await expect(cartBadge, `Cart badge should persist through refresh cycle ${i + 1}`).toHaveText('1');
    }
    
    // Verify cart functionality after rapid refreshes
    const removeButton = page.getByRole('button', { name: 'Remove' });
    await expect(removeButton, 'Remove button should remain functional after rapid refreshes').toBeVisible();
    
    // Test that cart operations still work
    await removeButton.click();
    await expect(cartBadge, 'Cart badge should disappear after removing item').not.toBeVisible();
  });

});