// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Browse new AWS items in What's New section (M01_BS_002)", () => {

  test("positive — browse and view AWS items in What's New section @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("what_s_new");
    await action.verifyUrlContains("whats-new", "Should navigate to What's New section");
    await action.verifyContainsText("what_s_new", "What's New", "What's New section should be visible with proper heading");
  });

});
