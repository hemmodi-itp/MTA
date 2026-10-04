// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Execute Open Action (M01_BS_007)", () => {

  test("positive — execute open action to render selected document @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("open");
    await action.verifyTitleContains("DOC-2024-Compliance-Report.pdf", "The page title should contain the name of the opened document");
  });

});
