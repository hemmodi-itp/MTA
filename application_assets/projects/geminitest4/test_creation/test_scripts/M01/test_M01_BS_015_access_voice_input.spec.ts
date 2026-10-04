// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access Voice Input (M01_BS_015)", () => {

  test("positive — clicking microphone button displays voice input interface @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("microphone", "Microphone button should be visible on the Gemini home page");
    await action.click("microphone");
    await action.waitForTimeout(1000);
  });

});
