// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/inventory.html
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("View Inventory Page and Verify Product List (M02_BS_001)", () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test("positive — view inventory page and verify navigation @smoke", async ({ action }) => {
    await action.navigate("/inventory.html");
    await action.verifyUrlContains("/inventory.html", "User should successfully navigate to and remain on the inventory page");
  });

});
