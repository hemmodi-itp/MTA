// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access comprehensive AWS product information from homepage (M01_BS_009)", () => {

  test("positive — access comprehensive AWS product information from homepage @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("solutions_4");
    await action.verifyContainsText("solutions_4", "AWS Products", "AWS Products heading should be visible on the products page");
    await action.verifyContainsText("solutions_4", "Amazon Web Services offers reliable, scalable, and inexpensive cloud computing services", "AWS service description should be displayed on the products page");
  });

});
