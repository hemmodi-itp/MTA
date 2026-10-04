// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/inventory.html
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Restrict Access to Inventory Page for Unauthenticated Users (M02_BS_016)", () => {


  test.beforeEach(async ({ page }) => {
    await page.goto("https://www.saucedemo.com/");
    await page.locator("[data-test='username']").fill("standard_user");
    await page.locator("[data-test='password']").fill("secret_sauce");
    await page.locator("[data-test='login-button']").click();
    await page.waitForTimeout(2000);
  });
  test("positive — unauthenticated navigation to inventory page redirects to login page @smoke", async ({ action }) => {
    await action.navigate("https://www.saucedemo.com/inventory.html");
    await action.verifyUrl("https://www.saucedemo.com/", "Unauthenticated user attempting to access inventory page should be redirected to the login page");
  });

});
