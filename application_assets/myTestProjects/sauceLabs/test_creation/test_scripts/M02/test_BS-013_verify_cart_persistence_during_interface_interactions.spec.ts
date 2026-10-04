import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.saucedemo.com/inventory.html';

test.describe('Verify Cart Persistence During Interface Interactions (BS-013)', () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test('positive — cart badge count persists through sort and menu interactions', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart first to establish preconditions
    await page.locator('.btn_inventory').first().click();
    
    // Step 1: Note the current cart badge count
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    await expect(cartBadge.locator('.shopping_cart_badge'), 'Cart badge should show initial count after adding item').toBeVisible();
    
    // Step 2: Change the product sort order using the dropdown
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await sortDropdown.selectOption('za');
    await expect(sortDropdown, 'Sort dropdown should be set to Name (Z to A)').toHaveValue('za');
    
    // Step 3: Open and close the hamburger menu
    const hamburgerMenu = page.getByRole('button', { name: 'Open Menu' });
    await hamburgerMenu.click();
    await expect(page.locator('.bm-menu'), 'Menu should be visible after clicking hamburger button').toBeVisible();
    
    const closeMenuButton = page.getByRole('button', { name: 'Close Menu' });
    await closeMenuButton.click();
    await expect(page.locator('.bm-menu'), 'Menu should be hidden after clicking close button').toBeHidden();
    
    // Step 4: Verify the cart badge count remains unchanged
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    await expect(cartBadge.locator('.shopping_cart_badge'), 'Cart badge should still be visible after interface interactions').toBeVisible();
    expect(finalCartCount, 'Cart badge count should remain unchanged after sorting and menu interactions').toBe(initialCartCount);
  });

  test('negative — cart persistence when sort dropdown receives invalid input', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    await page.locator('.btn_inventory').first().click();
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    
    // Attempt to inject script through sort dropdown
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await page.evaluate((dropdown) => {
      dropdown.value = '<script>alert("xss")</script>';
      dropdown.dispatchEvent(new Event('change'));
    }, await sortDropdown.elementHandle());
    
    // Verify cart persists despite invalid input
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    expect(finalCartCount, 'Cart badge count should persist even with invalid sort input').toBe(initialCartCount);
  });

  test('negative — cart persistence during rapid menu toggle with special characters', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    await page.locator('.btn_inventory').first().click();
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    
    // Rapidly toggle menu multiple times
    const hamburgerMenu = page.getByRole('button', { name: 'Open Menu' });
    for (let i = 0; i < 3; i++) {
      await hamburgerMenu.click();
      await page.getByRole('button', { name: 'Close Menu' }).click();
    }
    
    // Verify cart persists despite rapid interactions
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    expect(finalCartCount, 'Cart badge count should persist through rapid menu toggling').toBe(initialCartCount);
  });

  test('negative — cart persistence with SQL injection attempt in sort context', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    await page.locator('.btn_inventory').first().click();
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    
    // Attempt SQL injection through sort manipulation
    await page.evaluate(() => {
      const sortSelect = document.querySelector('.product_sort_container');
      if (sortSelect) {
        sortSelect.value = "'; DROP TABLE products; --";
        sortSelect.dispatchEvent(new Event('change'));
      }
    });
    
    // Verify cart persists despite injection attempt
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    expect(finalCartCount, 'Cart badge count should persist despite SQL injection attempt').toBe(initialCartCount);
  });

  test('negative — cart persistence when page elements are missing', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    await page.locator('.btn_inventory').first().click();
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    
    // Hide sort dropdown to simulate missing element
    await page.evaluate(() => {
      const sortDropdown = document.querySelector('.product_sort_container');
      if (sortDropdown) {
        sortDropdown.style.display = 'none';
      }
    });
    
    // Try to interact with hidden element
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    await expect(sortDropdown, 'Sort dropdown should be hidden').toBeHidden();
    
    // Verify cart still persists
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    expect(finalCartCount, 'Cart badge count should persist even when interface elements are missing').toBe(initialCartCount);
  });

  test('boundary — cart persistence with maximum sort operations', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    await page.locator('.btn_inventory').first().click();
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    
    // Perform maximum number of sort operations
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    const sortOptions = ['az', 'za', 'lohi', 'hilo'];
    
    for (let i = 0; i < 50; i++) {
      const option = sortOptions[i % sortOptions.length];
      await sortDropdown.selectOption(option);
    }
    
    // Verify cart persists after extensive sorting
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    expect(finalCartCount, 'Cart badge count should persist after maximum sort operations').toBe(initialCartCount);
  });

  test('boundary — cart persistence at session boundary with extended menu interaction', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add multiple items to test higher cart count
    const addButtons = page.locator('.btn_inventory');
    const buttonCount = Math.min(await addButtons.count(), 6);
    
    for (let i = 0; i < buttonCount; i++) {
      await addButtons.nth(i).click();
    }
    
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    
    // Extended menu interaction at boundary
    const hamburgerMenu = page.getByRole('button', { name: 'Open Menu' });
    await hamburgerMenu.click();
    
    // Navigate through all menu items without clicking
    const menuItems = page.locator('.menu-item');
    const menuCount = await menuItems.count();
    for (let i = 0; i < menuCount; i++) {
      await menuItems.nth(i).hover();
    }
    
    await page.getByRole('button', { name: 'Close Menu' }).click();
    
    // Verify cart persists at maximum item boundary
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    expect(finalCartCount, 'Cart badge count should persist at maximum item boundary with extended menu interaction').toBe(initialCartCount);
  });

  test('boundary — cart persistence with concurrent sort and menu operations', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Add item to cart
    await page.locator('.btn_inventory').first().click();
    const cartBadge = page.getByTestId('shopping-cart-link');
    const initialCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    
    // Perform concurrent operations at boundary
    const sortDropdown = page.getByRole('combobox', { name: 'Name (A to Z)\nName (Z to A)\nPrice (low to high)\nPrice (high to low)' });
    const hamburgerMenu = page.getByRole('button', { name: 'Open Menu' });
    
    // Simulate near-simultaneous operations
    await Promise.all([
      sortDropdown.selectOption('za'),
      hamburgerMenu.click()
    ]);
    
    await page.getByRole('button', { name: 'Close Menu' }).click();
    await sortDropdown.selectOption('lohi');
    
    // Verify cart persists through concurrent operations
    const finalCartCount = await cartBadge.locator('.shopping_cart_badge').textContent();
    expect(finalCartCount, 'Cart badge count should persist through concurrent sort and menu operations').toBe(initialCartCount);
  });

});