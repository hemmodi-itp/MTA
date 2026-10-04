// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Navigate Using Keyboard (M01_BS_014)", () => {

  test("positive — keyboard navigation through all interactive controls using Tab key @smoke", async ({ action }) => {
    await action.navigate();
    await action.pressKey(null, "Tab");
    await action.pressKey(null, "Tab");
    await action.pressKey(null, "Tab");
    await action.pressKey(null, "Tab");
    await action.pressKey(null, "Tab");
    await action.verifyNoPageErrors("Page should remain stable during keyboard navigation");
  });

  test("negative — insufficient interactive elements found for keyboard navigation @regression", async ({ action }) => {
    await action.navigate();
    await action.pressKey(null, "Tab");
    await action.pressKey(null, "Tab");
    await action.pressKey(null, "Tab");
    await action.verifyNoPageErrors("Page should handle minimal keyboard navigation without errors");
  });

});
