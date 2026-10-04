// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access BRD Compliance Criterion Level View (M01_BS_003)", () => {

  test("positive — open demo project @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("open_the_demo_project");
    await action.verifyUrlContains("project", "URL should contain project after opening the demo project");
  });

  test("positive — access BRD compliance criterion level view succeeds @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("brd_compliance_criterion_level");
    await action.verifyUrlContains("/compliance/brd/criterion-level", "URL should lead to the BRD compliance criterion level page");
    await action.verifyTitleContains("BRD Compliance Criterion Level View", "Page title should display BRD Compliance Criterion Level View");
  });

  test("negative — BRD compliance criterion level view fails to load @regression", async ({ action }) => {
    await action.navigate();
    await action.click("brd_compliance_criterion_level");
    await action.verifyUrlContains("/error/404", "URL should redirect to the 404 error page when BRD compliance criterion level view fails to load");
    await action.verifyTitleContains("Page Not Found", "Page title should display Page Not Found on failure");
  });

});
