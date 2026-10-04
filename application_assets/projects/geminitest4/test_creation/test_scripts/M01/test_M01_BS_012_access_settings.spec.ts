// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access Settings (M01_BS_012)", () => {

  test("positive — clicking settings icon opens the settings panel @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("settings");
    await action.verifyVisible("settings", "Settings panel should be visible after clicking the settings icon");
  });

});
