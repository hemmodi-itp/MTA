// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/partners/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Discover AWS Partner success stories and innovations (M04_BS_005)", () => {

  test("positive — discover AWS Partner success stories and innovations @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("explore_all_success_stories");
    await action.verifyVisible("explore_all_success_stories", "Partner Success with AWS section should be visible");
    await action.click("explore_all_success_stories");
    await action.verifyVisible("the_network_achieves_85_model_accuracy_in", "Partner success stories should be displayed after navigation");
    await action.verifyContainsText("the_network_achieves_85_model_accuracy_in", "machine learning solution on AWS", "Success story should contain innovation details driven by partners");
  });

});
