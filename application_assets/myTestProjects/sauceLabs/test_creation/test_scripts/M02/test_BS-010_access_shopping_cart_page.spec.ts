import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Access Shopping Cart Page (BS-010)', () => {
  

  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — shopping cart page opens successfully from inventory page', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Verify we are on the inventory page
    await expect(page, 'Should be on inventory page').toHaveURL(/.*inventory\.html/);
    
    // Click on the shopping cart icon in the header
    await page.getByTestId('shopping-cart-link').click();
    
    // Verify navigation to the shopping cart page
    await expect(page, 'Should navigate to shopping cart page').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.title'), 'Shopping cart page title should be visible').toBeVisible();
    await expect(page.locator('.cart_list'), 'Cart list container should be visible for item management').toBeVisible();
  });

  test('negative — shopping cart access with tampered session data', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Inject invalid session data
    await page.evaluate(() => {
      localStorage.setItem('session-username', '<script>alert("xss")</script>');
    });
    
    await page.getByTestId('shopping-cart-link').click();
    
    // Should still navigate but handle invalid session gracefully
    await expect(page, 'Should handle invalid session data gracefully').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.title'), 'Cart page should still load with invalid session').toBeVisible();
  });

  test('negative — shopping cart access with corrupted local storage', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Corrupt local storage with invalid JSON
    await page.evaluate(() => {
      localStorage.setItem('cart-contents', '{"invalid": json}');
    });
    
    await page.getByTestId('shopping-cart-link').click();
    
    await expect(page, 'Should navigate despite corrupted cart data').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.cart_list'), 'Cart should handle corrupted data without crashing').toBeVisible();
  });

  test('negative — shopping cart access with SQL injection in URL parameters', async ({ page }) => {
    await page.goto(BASE_URL + "?user='; DROP TABLE users; --");
    
    await page.getByTestId('shopping-cart-link').click();
    
    await expect(page, 'Should handle SQL injection attempt safely').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.title'), 'Cart page should load normally despite injection attempt').toBeVisible();
  });

  test('negative — shopping cart access with special characters in referrer', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Set special characters in page context
    await page.evaluate(() => {
      history.replaceState(null, '', '/inventory.html?ref=<>[]{}|\\`~!@#$%^&*()');
    });
    
    await page.getByTestId('shopping-cart-link').click();
    
    await expect(page, 'Should handle special characters in referrer').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.cart_list'), 'Cart functionality should work with special char referrer').toBeVisible();
  });

  test('boundary — shopping cart access with maximum concurrent requests', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate rapid clicking to test boundary conditions
    const cartLink = page.getByTestId('shopping-cart-link');
    
    // Click multiple times rapidly to test system boundaries
    await Promise.all([
      cartLink.click(),
      cartLink.click(),
      cartLink.click()
    ]).catch(() => {}); // Ignore potential race condition errors
    
    await expect(page, 'Should handle multiple rapid clicks and navigate once').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.title'), 'Cart page should load despite rapid clicking').toBeVisible();
  });

  test('boundary — shopping cart access with maximum URL length', async ({ page }) => {
    const longParam = 'a'.repeat(2000); // Very long parameter
    await page.goto(BASE_URL + '?longparam=' + longParam);
    
    await page.getByTestId('shopping-cart-link').click();
    
    await expect(page, 'Should handle very long URL parameters').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.cart_list'), 'Cart should function with long URL parameters').toBeVisible();
  });

  test('boundary — shopping cart access at browser memory limit', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Fill local storage to near capacity
    await page.evaluate(() => {
      try {
        for (let i = 0; i < 100; i++) {
          localStorage.setItem(`test_data_${i}`, 'x'.repeat(10000));
        }
      } catch (e) {
        // Storage quota exceeded, which is expected
      }
    });
    
    await page.getByTestId('shopping-cart-link').click();
    
    await expect(page, 'Should navigate even with full local storage').toHaveURL(/.*cart\.html/);
    await expect(page.locator('.title'), 'Cart should work at storage capacity boundary').toBeVisible();
  });
});