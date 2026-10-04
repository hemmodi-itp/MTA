// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/partners/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Browse latest updates in What's New section (M04_BS_004)", () => {

  test("positive — browse and view details in What's New section @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("what_s_new_posts_read_about_the_latest");
    await action.verifyVisible("what_s_new_posts_read_about_the_latest", "What's New section should be visible on the page");
    await action.verifyContainsText("what_s_new_posts_read_about_the_latest", "What's New", "What's New heading should be displayed");
    await action.click("what_s_new_posts_read_about_the_latest");
    await action.verifyContainsText("what_s_new_posts_read_about_the_latest", "AWS", "Content should contain AWS Partner program related information");
  });

});
