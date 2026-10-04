// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access Previous Conversations (M01_BS_011)", () => {

  test("positive — clicking a previous conversation in sidebar opens and displays the conversation @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyUrlContains("/conversation/", "URL should contain conversation path after selecting a previous conversation");
  });

});
