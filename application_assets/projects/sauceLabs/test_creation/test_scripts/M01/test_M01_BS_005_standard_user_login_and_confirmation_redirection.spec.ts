// Base URL (from project.yaml, resolved via playwright.config.ts): https://www.saucedemo.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Standard User Login and Confirmation Redirection (M01_BS_005)", () => {

  test("positive — standard user can enter login credentials @smoke", async ({ action }) => {
    await action.navigate();
    await action.enterText("username", "standard_user");
    await action.enterText("password", "secret_sauce");
  });

});
