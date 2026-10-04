// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Guest user initiates partner registration process (M04_BS_008)", () => {

  test("positive — guest user initiates partner registration process and reaches login page @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyContainsText("contact_us_7", "AWS Partner Network", "Partner section heading should be visible on the page");
    await action.verifyContainsText("contact_us_7", "Join thousands of partners", "Partner content should be displayed to encourage registration");
    await action.verifyContainsText("contact_us_7", "sign in to aws console", "Sign in link should be available for partner registration");
    await action.verifyUrl("https://signin.aws.amazon.com/signin", "User should be redirected to AWS login page to complete partner registration");
  });

});
