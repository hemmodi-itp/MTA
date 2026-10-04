// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Explore AWS service updates through What's New section (M01_BS_010)", () => {

  test("positive — explore AWS service updates through What's New section @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyTitleContains("AWS", "Page should contain AWS in title");
    await action.verifyContainsText("a_loc_0068", "What's New", "What's New section should be visible on the page");
    await action.click("a_loc_0068");
    await action.verifyUrlContains("aws", "Should navigate to AWS updates or features page");
    await action.verifyVisible("a_loc_0068", "AWS service updates content should be displayed");
  });

});
