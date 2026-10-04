// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Switch AI Model (M01_BS_007)", () => {

  test("positive — switching AI model from dropdown activates the selected model @smoke", async ({ action }) => {
    await action.navigate();
    await action.selectDropdownByText("flash", "GPT-4");
    await action.verifyVisible("flash", "Selected AI model should be visible and active after selection");
  });

  test("negative — selecting invalid model shows appropriate error @regression", async ({ action }) => {
    await action.navigate();
    await action.selectDropdownByText("flash", "");
    await action.verifyContainsText("flash", "Please select a valid AI model", "Error message should appear when no model is selected");
  });

});
