// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Navigate to Amazon QuickSight through Products menu (M01_BS_011)", () => {

  test("positive — navigate to Amazon QuickSight through Products menu succeeds @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("solutions_4");
    await action.verifyUrlContains("/quicksight", "User should navigate to Amazon QuickSight service page");
    await action.verifyContainsText("solutions_4", "Amazon QuickSight", "Amazon QuickSight heading should be visible on the service page");
  });

});
