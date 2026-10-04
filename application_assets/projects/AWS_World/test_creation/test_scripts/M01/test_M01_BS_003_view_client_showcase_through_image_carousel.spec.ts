// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("View client showcase through image carousel (M01_BS_003)", () => {

  test("positive — view client showcase through image carousel navigation @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("previous_slide");
    await action.verifyContainsText("previous_slide", "Our Client Success Stories", "Carousel section should display the expected heading for client showcase");
    await action.click("next_slide");
    await action.verifyVisible("next_slide", "Next slide should be visible after clicking next navigation");
    await action.click("previous_slide");
    await action.verifyVisible("previous_slide", "Previous slide should be visible after clicking previous navigation");
  });

});
