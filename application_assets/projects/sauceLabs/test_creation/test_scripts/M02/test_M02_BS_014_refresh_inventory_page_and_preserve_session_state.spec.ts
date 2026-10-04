// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/inventory.html
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Refresh Inventory Page and Preserve Session State (M02_BS_014)", () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test("positive — refreshing the inventory page reloads successfully and preserves session state @smoke", async ({ action }) => {
    await action.navigate();
    await action.reload();
    await action.verifyUrl("https://www.saucedemo.com/inventory.html", "Inventory page reloads successfully and preserves the active session URL");
  });

});
