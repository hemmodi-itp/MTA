// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Explore AWS products information from homepage (M01_BS_005)", () => {

  test("positive — explore AWS products information from homepage @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("navigate_products");
    await action.verifyContainsText("navigate_products", "Products", "Products section should be accessible from homepage");
    await action.click("explore_aws_for_your_industry");
    await action.verifyVisible("financial_services_develop_innovative_and_secure", "Financial services product information should be visible");
    await action.verifyVisible("healthcare_and_life_sciences_accelerate", "Healthcare and life sciences product information should be visible");
    await action.verifyVisible("government_solutions_designed_to_help_government", "Government solutions product information should be visible");
  });

});
