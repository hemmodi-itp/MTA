// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Complete automated workflow execution for partner onboarding (M04_BS_006)", () => {

  test("positive — complete automated workflow execution for partner onboarding succeeds @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyUrl("/aws/partner/onboarding/complete", "User should be on the partner onboarding completion page");
    await action.verifyNoPageErrors("Both partner workflows should execute without any page errors");
  });

});
