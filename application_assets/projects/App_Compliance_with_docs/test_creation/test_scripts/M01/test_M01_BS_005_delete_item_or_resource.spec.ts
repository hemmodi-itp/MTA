// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:5173/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Delete Item or Resource (M01_BS_005)", () => {

  test("positive — delete target item or resource from the system @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("delete");
  });

  test("positive — open and create projects in demo area @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("open");
    await action.click("new_project_2");
  });

});
