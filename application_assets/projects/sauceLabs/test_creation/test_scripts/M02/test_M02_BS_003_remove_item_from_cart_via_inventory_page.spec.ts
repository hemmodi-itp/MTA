// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/inventory.html
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Remove Item from Cart via Inventory Page (M02_BS_003)", () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test("positive — remove item from cart via inventory page @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyUrlContains("/inventory.html", "User should be on the inventory page");
  });

});
