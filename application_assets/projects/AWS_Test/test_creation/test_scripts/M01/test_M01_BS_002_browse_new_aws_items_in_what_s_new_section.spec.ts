// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Browse new AWS items in What's New section (M01_BS_002)", () => {

  test("positive — browse new AWS items in What's New section and view details @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("a_loc_0068");
    await action.verifyVisible("a_loc_0068", "What's New section should be visible on the homepage");
    await action.verifyContainsText("a_loc_0068", "What's New with AWS", "What's New section should display the correct heading");
    await action.click("a_loc_0068");
    await action.verifyUrl("/about-aws/whats-new/2023/", "User should be redirected to the What's New details page");
  });

  test("negative — What's New section unavailable or content missing @regression", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("a_loc_0068");
    await action.verifyHidden("a_loc_0068", "What's New section should handle unavailable content gracefully");
  });

});
