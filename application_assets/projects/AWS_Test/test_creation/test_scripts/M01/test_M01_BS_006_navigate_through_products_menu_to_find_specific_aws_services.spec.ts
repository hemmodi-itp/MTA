// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Navigate through Products menu to find specific AWS services (M01_BS_006)", () => {

  test("positive — navigate through Products menu to find Amazon Quick service @smoke", async ({ action }) => {
    await action.navigate();
    await action.verifyVisible("solutions_4", "Products menu should be visible in navigation");
    await action.click("solutions_4");
    await action.verifyUrl("/amazon-quick", "User should be redirected to Amazon Quick service page");
  });

});
