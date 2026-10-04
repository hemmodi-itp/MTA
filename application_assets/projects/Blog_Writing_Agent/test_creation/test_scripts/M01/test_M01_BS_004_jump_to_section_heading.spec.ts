// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:8501/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Jump to Section Heading (M01_BS_004)", () => {

  test("positive — jump to section heading navigates viewport to target anchor @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("link_to_heading");
    await action.verifyUrlContains("#key-features", "URL should include the section anchor #key-features after clicking the heading link");
  });

});
