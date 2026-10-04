// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access BRD Compliance Criterion Level View (GEN_BS_003)", () => {

  test("positive — access BRD compliance criterion level view @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("brd_compliance_criterion_level");
    await action.verifyUrlContains("/compliance/brd/criterion-level", "Application should navigate to the BRD compliance criterion level view");
  });

});
