// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Open Demo Project (GEN_BS_002)", () => {

  test("positive — open demo project successfully loads project page @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("open_the_demo_project");
    await action.verifyUrlContains("/projects/demo", "URL should contain /projects/demo after opening the demo project");
    await action.verifyTitleContains("Demo Project", "Page title should contain Demo Project");
  });

  test("positive — switch to dark mode toggles dark theme @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("switch_to_dark_mode");
  });

  test("negative — opening demo project handles load failure state @regression", async ({ action }) => {
    await action.navigate();
    await action.click("open_the_demo_project");
    await action.verifyUrlContains("/error/404", "URL should redirect to 404 error page when demo project content fails to load");
  });

});
