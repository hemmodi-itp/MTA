// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/partners/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Navigate between different Partner sections using navigation bar (M04_BS_001)", () => {

  test("positive — navigate to Partner Solutions section using navigation bar @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("partner_programs", "Partner navigation should be visible");
    await action.verifyCount("partner_programs", 3, "Navigation should have at least 3 items");
    await action.click("partner_programs");
    await action.verifyUrl("/partners/solutions", "User should be navigated to the Partner Solutions section");
    await action.verifyContainsText("aws_partners_4", "AWS Partner Solutions", "Section heading should display correctly");
    await action.verifyContainsText("partner_programs", "partner programs", "Expected content should be present in the section");
  });

});
