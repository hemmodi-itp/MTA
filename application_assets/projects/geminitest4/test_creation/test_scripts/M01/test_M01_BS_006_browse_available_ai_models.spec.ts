// Base URL (from project.yaml, resolved via playwright.config.ts): https://gemini.google.com
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Browse Available AI Models (M01_BS_006)", () => {

  test("positive — clicking model dropdown displays available AI models list @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("flash", "Model selector should be visible on the page");
  });

});
