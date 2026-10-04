// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access Shopflow Demo (M01_BS_006)", () => {

  test("positive — user accesses Shopflow demo project successfully @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("shopflow_demo");
    await action.verifyUrlContains("/demo/shopflow", "URL should contain /demo/shopflow after clicking the Shopflow demo option");
    await action.verifyTitleContains("Shopflow Demo", "Page title should contain Shopflow Demo");
  });

});
