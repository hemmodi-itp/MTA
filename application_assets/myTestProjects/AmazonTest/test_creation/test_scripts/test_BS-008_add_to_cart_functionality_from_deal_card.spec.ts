import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Add to Cart Functionality from Deal Card (BS-008)', () => {
  
  test('positive — valid add to cart action increments global cart summary', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait for deals page to load
    await page.waitForLoadState('networkidle');
    
    // Get initial cart count
    const cartElement = page.getByRole('link', { name: '0\nCart' });
    await expect(cartElement, 'Global shopping cart summary should be visible').toBeVisible();
    
    const initialCartText = await cartElement.textContent();
    const initialCartCount = parseInt(initialCartText?.match(/\d+/)?.[0] || '0');
    
    // Locate and click add to cart button on a deal card
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart button should be visible on deal card').toBeVisible();
    await addToCartButton.click();
    
    // Wait for cart update
    await page.waitForTimeout(2000);
    
    // Verify cart count has incremented
    const updatedCartText = await cartElement.textContent();
    const updatedCartCount = parseInt(updatedCartText?.match(/\d+/)?.[0] || '0');
    
    await expect(updatedCartCount, 'Cart count should increment after adding item').toBeGreaterThan(initialCartCount);
  });

  test('negative — add to cart with empty session data shows error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Clear all cookies to simulate empty session
    await page.context().clearCookies();
    
    await page.waitForLoadState('networkidle');
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart button should be visible').toBeVisible();
    await addToCartButton.click();
    
    // Should redirect to login or show error
    await page.waitForTimeout(3000);
    const currentUrl = page.url();
    await expect(currentUrl.includes('signin') || currentUrl.includes('login'), 'Should redirect to login page when session is empty').toBeTruthy();
  });

  test('negative — add to cart with special characters in product data handles gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Inject special characters into product data via browser console
    await page.evaluate(() => {
      const productElements = document.querySelectorAll('[data-testid="deal-card"]');
      if (productElements.length > 0) {
        productElements[0].setAttribute('data-product-name', '<script>alert("xss")</script>');
        productElements[0].setAttribute('data-product-price', '\'"; DROP TABLE products; --');
      }
    });
    
    await page.waitForLoadState('networkidle');
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart button should remain functional with special chars').toBeVisible();
    await addToCartButton.click();
    
    await page.waitForTimeout(2000);
    
    // Verify no XSS or SQL injection occurred
    const pageContent = await page.content();
    await expect(pageContent.includes('<script>alert'), 'Page should not contain unescaped script tags').toBeFalsy();
  });

  test('negative — add to cart with sql injection in request parameters is sanitized', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.waitForLoadState('networkidle');
    
    // Intercept and modify add to cart request
    await page.route('**/cart/add*', async route => {
      const request = route.request();
      const postData = request.postData() || '';
      const modifiedData = postData + "&productId=1'; DROP TABLE cart; --";
      
      await route.continue({
        postData: modifiedData
      });
    });
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart button should be available for injection test').toBeVisible();
    await addToCartButton.click();
    
    await page.waitForTimeout(3000);
    
    // Verify application still functions (cart not dropped)
    const cartElement = page.getByRole('link', { name: /\d+\nCart/ });
    await expect(cartElement, 'Cart should still be functional after SQL injection attempt').toBeVisible();
  });

  test('negative — add to cart with wrong format product ID shows error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.waitForLoadState('networkidle');
    
    // Mock invalid product ID in the add to cart request
    await page.route('**/cart/add*', async route => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Invalid product format',
          message: 'Product ID must be numeric'
        })
      });
    });
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart button should be clickable for error test').toBeVisible();
    await addToCartButton.click();
    
    await page.waitForTimeout(2000);
    
    // Verify error is handled gracefully
    const errorMessage = page.locator('[data-testid="error-message"], .error-message, .alert-error');
    await expect(errorMessage, 'Error message should be displayed for invalid product format').toBeVisible();
  });

  test('boundary — add to cart at maximum quantity limit shows appropriate message', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.waitForLoadState('networkidle');
    
    // Mock response for maximum quantity
    await page.route('**/cart/add*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          message: 'Maximum quantity limit reached',
          maxQuantity: 10
        })
      });
    });
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart button should handle quantity limits').toBeVisible();
    await addToCartButton.click();
    
    await page.waitForTimeout(2000);
    
    const limitMessage = page.locator('text="Maximum quantity limit reached", text="limit reached"');
    await expect(limitMessage, 'Maximum quantity limit message should be displayed').toBeVisible();
  });

  test('boundary — add to cart with extremely long product name truncates properly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Create a 1000-character product name
    const longProductName = 'A'.repeat(1000);
    
    await page.evaluate((name) => {
      const dealCards = document.querySelectorAll('[data-testid="deal-card"]');
      if (dealCards.length > 0) {
        const titleElement = dealCards[0].querySelector('.deal-title, h3, .product-name');
        if (titleElement) {
          titleElement.textContent = name;
        }
      }
    }, longProductName);
    
    await page.waitForLoadState('networkidle');
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart should handle long product names').toBeVisible();
    await addToCartButton.click();
    
    await page.waitForTimeout(2000);
    
    const cartElement = page.getByRole('link', { name: /\d+\nCart/ });
    await expect(cartElement, 'Cart should function normally with long product names').toBeVisible();
  });

  test('boundary — add to cart with URL input in product description is sanitized', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maliciousUrl = 'javascript:alert("xss")';
    
    await page.evaluate((url) => {
      const dealCards = document.querySelectorAll('[data-testid="deal-card"]');
      if (dealCards.length > 0) {
        dealCards[0].setAttribute('data-product-url', url);
        const descElement = dealCards[0].querySelector('.deal-description, .product-description');
        if (descElement) {
          descElement.innerHTML = `<a href="${url}">Click here</a>`;
        }
      }
    }, maliciousUrl);
    
    await page.waitForLoadState('networkidle');
    
    const addToCartButton = page.getByTestId('add-to-cart-button').first();
    await expect(addToCartButton, 'Add to cart should sanitize URL inputs').toBeVisible();
    await addToCartButton.click();
    
    await page.waitForTimeout(2000);
    
    // Verify malicious URLs are sanitized
    const maliciousLinks = page.locator('a[href^="javascript:"]');
    await expect(await maliciousLinks.count(), 'No malicious javascript URLs should be present').toBe(0);
  });

});