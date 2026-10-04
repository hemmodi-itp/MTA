// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:8501/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Stop Active Process (M01_BS_003)", () => {

  test("positive — user clicks stop button to halt active process @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("stop");
  });

});
