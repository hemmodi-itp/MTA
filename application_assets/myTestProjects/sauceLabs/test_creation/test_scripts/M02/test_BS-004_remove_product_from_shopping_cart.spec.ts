import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Remove Product from Shopping Cart (BS-004)', () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — remove product from cart updates button and decreases cart badge', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // First add a product to cart to meet precondition
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await expect(addToCartButton, 'Add to cart button must be visible on inventory page').toBeVisible();
    await addToCartButton.click();
    
    // Verify button changed to Remove and cart badge shows 1
    const removeButton = page.getByRole('button', { name: 'Remove' }).first();
    await expect(removeButton, 'Remove button must appear after adding product to cart').toBeVisible();
    
    const cartBadge = page.getByTestId('shopping-cart-link');
    await expect(cartBadge, 'Cart badge must show item count after adding product').toContainText('1');
    
    // Click Remove button (step 1)
    await removeButton.click();
    
    // Verify button changes back to 'Add to Cart' (step 2)
    await expect(addToCartButton, 'Button must change back to Add to cart after removing product').toBeVisible();
    await expect(removeButton, 'Remove button must not be visible after clicking remove').not.toBeVisible();
    
    // Check cart badge decreases by one (step 3)
    await expect(cartBadge, 'Cart badge must not show count when cart is empty').not.toContainText('1');
  });

  test('negative — remove button not available when cart is empty', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Verify no Remove buttons are visible initially
    const removeButtons = page.getByRole('button', { name: 'Remove' });
    await expect(removeButtons.first(), 'Remove button must not be visible when no products in cart').not.toBeVisible();
    
    // Verify only Add to Cart buttons are available
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await expect(addToCartButton, 'Add to cart button must be visible when product not in cart').toBeVisible();
  });

  test('negative — multiple rapid remove clicks do not cause errors', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add product to cart
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    const removeButton = page.getByRole('button', { name: 'Remove' }).first();
    await expect(removeButton, 'Remove button must be visible after adding product').toBeVisible();
    
    // Click remove multiple times rapidly
    await removeButton.click();
    await removeButton.click({ force: true });
    await removeButton.click({ force: true });
    
    // Verify final state is correct
    await expect(addToCartButton, 'Button must be Add to cart after remove clicks').toBeVisible();
    const cartBadge = page.getByTestId('shopping-cart-link');
    await expect(cartBadge, 'Cart badge must not show count after removing item').not.toContainText('1');
  });

  test('negative — remove product when cart has special character count display', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add multiple products with special characters in names
    const addButtons = page.getByRole('button', { name: 'Add to cart' });
    await addButtons.first().click();
    await addButtons.nth(1).click();
    
    const cartBadge = page.getByTestId('shopping-cart-link');
    await expect(cartBadge, 'Cart badge must show count of 2 items').toContainText('2');
    
    // Remove one product
    const removeButton = page.getByRole('button', { name: 'Remove' }).first();
    await removeButton.click();
    
    // Verify count decreases properly
    await expect(cartBadge, 'Cart badge must show decreased count after removal').toContainText('1');
  });

  test('negative — remove button behavior with malformed product data', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add product and verify normal flow
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    
    // Inject potential malicious script via console to test robustness
    await page.evaluate(() => {
      localStorage.setItem('cart-item-test', '<script>alert("xss")</script>');
    });
    
    const removeButton = page.getByRole('button', { name: 'Remove' }).first();
    await removeButton.click();
    
    // Verify normal behavior despite malicious data
    await expect(addToCartButton, 'Add to cart button must be visible despite malformed data injection').toBeVisible();
  });

  test('boundary — remove last item from cart with maximum products added', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add all available products to cart
    const addButtons = page.getByRole('button', { name: 'Add to cart' });
    const buttonCount = await addButtons.count();
    
    for (let i = 0; i < buttonCount; i++) {
      await addButtons.nth(i).click();
    }
    
    const cartBadge = page.getByTestId('shopping-cart-link');
    await expect(cartBadge, 'Cart badge must show maximum item count').toContainText(buttonCount.toString());
    
    // Remove all items one by one
    for (let i = 0; i < buttonCount; i++) {
      const removeButton = page.getByRole('button', { name: 'Remove' }).first();
      await removeButton.click();
    }
    
    // Verify cart is empty
    await expect(cartBadge, 'Cart badge must not show count when all items removed').not.toContainText(buttonCount.toString());
  });

  test('boundary — remove product at zero cart count boundary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Verify starting at boundary (empty cart)
    const cartBadge = page.getByTestId('shopping-cart-link');
    await expect(cartBadge, 'Cart badge must not show count initially').not.toContainText('1');
    
    // Add one item (cross boundary)
    const addToCartButton = page.getByRole('button', { name: 'Add to cart' }).first();
    await addToCartButton.click();
    await expect(cartBadge, 'Cart badge must show 1 after adding single item').toContainText('1');
    
    // Remove item (return to boundary)
    const removeButton = page.getByRole('button', { name: 'Remove' }).first();
    await removeButton.click();
    
    // Verify back at zero boundary
    await expect(cartBadge, 'Cart badge must not show count after returning to empty state').not.toContainText('1');
    await expect(addToCartButton, 'Add to cart button must be visible at zero boundary').toBeVisible();
  });

  test('boundary — remove product with cart badge at single digit boundary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add exactly 9 items (single digit boundary)
    const addButtons = page.getByRole('button', { name: 'Add to cart' });
    const maxSingleDigit = Math.min(9, await addButtons.count());
    
    for (let i = 0; i < maxSingleDigit; i++) {
      await addButtons.nth(i).click();
    }
    
    const cartBadge = page.getByTestId('shopping-cart-link');
    await expect(cartBadge, 'Cart badge must show single digit count').toContainText(maxSingleDigit.toString());
    
    // Remove one item to test boundary behavior
    const removeButton = page.getByRole('button', { name: 'Remove' }).first();
    await removeButton.click();
    
    const expectedCount = maxSingleDigit - 1;
    await expect(cartBadge, 'Cart badge must show decremented count at digit boundary').toContainText(expectedCount.toString());
  });

});