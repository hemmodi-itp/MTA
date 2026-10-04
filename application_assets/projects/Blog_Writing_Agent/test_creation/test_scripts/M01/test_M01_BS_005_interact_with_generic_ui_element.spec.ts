// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:8501/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Interact with Generic UI Element (M01_BS_005)", () => {

  test("positive — interact with target generic UI element @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("button_loc_0001", "Target interactive element LOC-0001 should be displayed on the active page");
    await action.click("button_loc_0001");
  });

  test("positive — interact with main menu element @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("main_menu", "Main menu element should be visible on the page");
    await action.click("main_menu");
  });

  test("positive — interact with deploy element @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("deploy", "Deploy element should be visible on the page");
    await action.click("deploy");
  });

});
