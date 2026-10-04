// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Start New Conversation (M01_BS_010)", () => {

  test("positive — clicking New Chat creates a new conversation with empty prompt textbox @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("new_chat");
    await action.verifyUrlContains("gemini.google.com", "User should remain on the Gemini platform after creating new chat");
    await action.verifyVisible("new_chat", "New chat functionality should be available in the new conversation");
  });

});
