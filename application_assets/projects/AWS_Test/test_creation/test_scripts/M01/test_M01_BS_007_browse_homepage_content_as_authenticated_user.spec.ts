// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Browse homepage content as authenticated user (M01_BS_007)", () => {

  test("positive — authenticated user can browse all homepage content sections @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("navigate_products_12", "Homepage navigation bar should be accessible to authenticated users");
    await action.verifyContainsText("navigate_products_12", "What's New", "What's New section should be visible and contain latest AWS updates");
    await action.verifyVisible("navigate_products_12", "Image carousel should display client images for authenticated users");
    await action.verifyContainsText("navigate_products_12", "customer success stories", "Customer success stories section should be accessible in story cards");
  });

});
