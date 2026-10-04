// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("View client images through image carousel (M01_BS_003)", () => {

  test("positive — view and navigate through client images in carousel @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("overview_3");
    await action.verifyVisible("overview_3", "Client carousel section should be visible on homepage");
    await action.verifyContainsText("overview_3", "Our Trusted Clients", "Carousel should display the expected heading");
    await action.verifyCount("overview_3", 3, "Carousel should contain at least 3 client images");
  });

});
