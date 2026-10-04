// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Switch Application Theme to Dark Mode (M01_BS_001)", () => {

  test("positive — switch application visual theme to dark mode @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("switch_to_dark_mode");
    await action.verifyVisible("switch_to_dark_mode", "Dark mode toggle control should remain visible and accessible after switching theme");
  });

});
