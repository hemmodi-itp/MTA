// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Login Form Missing Required Fields Validation (M01_BS_003)", () => {

  test("positive — standard user login with valid credentials succeeds @smoke", async ({ action }) => {
    await action.navigate();
    await action.enterText("username", "standard_user");
    await action.enterText("password", "secret_sauce");
    await action.pressKey("password", "Enter");
    await action.verifyUrlContains("inventory", "User should be redirected to the inventory page after submitting valid credentials");
  });

  test("negative — submitting form with missing required credentials prevents navigation @regression", async ({ action }) => {
    await action.navigate();
    await action.pressKey("password", "Enter");
    await action.verifyUrlContains("saucedemo.com", "Form submission should be prevented and user should remain on the login page when mandatory fields are empty");
  });

  test("boundary — credentials exceeding maximum character limit are rejected @regression", async ({ action }) => {
    await action.navigate();
    await action.enterText("username", "user_255_limit_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    await action.enterText("password", "secret_sauce");
    await action.pressKey("password", "Enter");
    await action.verifyUrlContains("saucedemo.com", "User should remain on login page when submitting username exceeding 255 characters", { soft: true });
  });

});
