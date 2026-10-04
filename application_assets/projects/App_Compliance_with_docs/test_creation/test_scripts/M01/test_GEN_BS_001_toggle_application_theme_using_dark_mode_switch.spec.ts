// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Toggle Application Theme using Dark Mode Switch (GEN_BS_001)", () => {

  test("positive — toggle application theme to dark mode using dark mode switch @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("switch_to_dark_mode");
    await action.verifyVisible("switch_to_dark_mode", "Dark mode switch should be visible on the page after toggling theme");
  });

});
