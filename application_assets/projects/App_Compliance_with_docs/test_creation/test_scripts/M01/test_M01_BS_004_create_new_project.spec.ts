// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Create New Project (M01_BS_004)", () => {

  test("positive — clicking new project button initiates new project creation workflow @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("new_project_2");
    await action.verifyUrlContains("/projects/new", "Clicking New Project should navigate to the project creation URL");
    await action.verifyTitleContains("Create New Project", "Page title should reflect the project creation screen");
  });

});
