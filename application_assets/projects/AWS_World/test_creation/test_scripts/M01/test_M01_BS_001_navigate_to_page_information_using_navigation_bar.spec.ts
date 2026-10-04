// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Navigate to page information using navigation bar (M01_BS_001)", () => {

  test("positive — navigation bar items all reach their expected pages @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("discover_aws");
    await action.verifyUrlContains("aws", "Discover AWS link should navigate to an AWS-related page");
    await action.goBack();
    await action.click("navigate_products");
    await action.verifyUrlContains("products", "Products link should navigate to a products page");
    await action.goBack();
    await action.click("solutions");
    await action.verifyUrlContains("solutions", "Solutions link should navigate to a solutions page");
    await action.goBack();
    await action.click("resources");
    await action.verifyUrlContains("resources", "Resources link should navigate to a resources page");
  });

});
