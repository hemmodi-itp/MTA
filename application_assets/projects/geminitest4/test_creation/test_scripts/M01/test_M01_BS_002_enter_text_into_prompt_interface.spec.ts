// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Enter Text into Prompt Interface (M01_BS_002)", () => {

  test("positive — enter text into prompt interface displays the text @smoke", async ({ action }) => {
    await action.navigate();
  });

  test("negative — empty prompt input shows validation error @regression", async ({ action }) => {
    await action.navigate();
  });

});
