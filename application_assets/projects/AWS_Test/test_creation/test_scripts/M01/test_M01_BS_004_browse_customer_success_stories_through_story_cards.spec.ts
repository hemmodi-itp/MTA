// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Browse customer success stories through story cards (M01_BS_004)", () => {

  test("positive — browse customer success stories through story cards @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("aws");
    await action.verifyVisible("aws", "Customer success stories should be displayed");
    await action.verifyCount("aws", 3, "At least 3 customer story cards should be visible");
    await action.click("aws");
    await action.verifyContainsText("aws", "customer testimonials and success cases", "Story details should contain customer testimonials and success cases");
  });

  test("negative — customer story cards section not available or content missing @regression", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("aws");
    await action.verifyCount("aws", 0, "No customer story cards should be available when content is missing");
  });

});
