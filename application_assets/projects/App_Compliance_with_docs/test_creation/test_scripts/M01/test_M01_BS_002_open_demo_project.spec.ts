// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Open Demo Project (M01_BS_002)", () => {

  test("positive — user opens and explores the demo project @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("open_the_demo_project");
    await action.verifyUrlContains("/projects/demo", "URL should contain /projects/demo after clicking open demo project");
    await action.verifyTitleContains("Demo Project", "Page title should contain Demo Project after opening the demo project");
  });

});
