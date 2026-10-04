// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Access Gemini Home Page Interface (M01_BS_001)", () => {

  test("positive — Gemini Home page displays all required UI components @smoke", async ({ action }) => {
    await action.navigate("/gemini/home");
    await action.verifyVisible("open_sidebar", "Sidebar should be displayed on the Home page");
    await action.verifyVisible("microphone", "Microphone button should be displayed on the Home page");
  });

});
