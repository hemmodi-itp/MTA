// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Create a New Project (GEN_BS_004)", () => {

  test("positive — user initiates creation of a new project @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("new_project_2");
    await action.verifyUrlContains("/projects/new", "The application should open the project creation workflow");
  });

});
