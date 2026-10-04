// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:8501/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Navigate to Main Menu (M01_BS_001)", () => {

  test("positive — user opens the main menu to access navigation options @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("main_menu");
  });

});
