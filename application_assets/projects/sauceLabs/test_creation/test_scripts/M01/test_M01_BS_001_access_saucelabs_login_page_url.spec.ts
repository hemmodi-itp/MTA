// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access SauceLabs Login Page URL (M01_BS_001)", () => {

  test("positive — unauthenticated visitor can access the SauceLabs login page @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyUrlContains("saucedemo.com", "SauceLabs login page URL should be loaded successfully");
    await action.verifyVisible("username", "Username input field should be visible on the login page");
    await action.verifyVisible("password", "Password input field should be visible on the login page");
  });

  test("negative — accessing an invalid page URL fails to load the login form @regression", async ({ action }) => {
    await action.navigate("https://www.saucedemo.com/invalid-page");
    await action.verifyHidden("username", "Login form username field should not be visible when navigating to an invalid page URL");
  });

});
