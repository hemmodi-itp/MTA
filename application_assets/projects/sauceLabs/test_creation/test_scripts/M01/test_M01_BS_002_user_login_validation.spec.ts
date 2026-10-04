// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("User Login Validation (M01_BS_002)", () => {

  test("positive — authenticate standard user with valid credentials @smoke", async ({ action }) => {
    await action.navigate();
    await action.enterText("username", "standard_user");
    await action.enterText("password", "secret_sauce");
  });

});
