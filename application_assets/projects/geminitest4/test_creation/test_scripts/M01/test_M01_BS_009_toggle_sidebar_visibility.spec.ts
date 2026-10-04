// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Toggle Sidebar Visibility (M01_BS_009)", () => {

  test("positive — sidebar toggle button collapses and expands the sidebar @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("open_sidebar");
    await action.verifyHidden("open_sidebar", "Sidebar should be collapsed after clicking toggle button");
    await action.click("open_sidebar");
    await action.verifyVisible("open_sidebar", "Sidebar should be expanded after clicking toggle button again");
  });

});
