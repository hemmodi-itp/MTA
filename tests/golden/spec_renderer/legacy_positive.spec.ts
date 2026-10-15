// Base URL (from project.yaml, resolved via playwright.config.ts): http://127.0.0.1:8765
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ baseURL: "http://127.0.0.1:8765" });

test.describe("Login (M01_BS_001)", () => {

  test("log in as alice @smoke", async ({ action }) => {
    await action.navigate("/login");
    await action.enterText("username", "alice");
    await action.enterText("password", "alice-pass-1");
    await action.click("login_button");
    await action.verifyUrlContains("/products");
    await action.verifyText("current_user", "alice", "Signed-in user is shown");
  });

  test("wrong password is rejected @regression", async ({ action }) => {
    await action.navigate("/login");
    await action.enterText("username", "alice");
    await action.enterText("password", "nope");
    await action.click("login_button");
    await action.verifyVisible("login_error", "An error is shown", { soft: true });
  });

});
