// Base URL (from project.yaml, resolved via playwright.config.ts): http://localhost:8501/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Deploy Blog Agent Service (M01_BS_002)", () => {

  test("positive — clicking deploy button initiates deployment for blog agent service @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("deploy");
    await action.verifyUrlContains("/control-panel/deployments/blog-agent/status", "URL should navigate to the blog agent deployment status page after initiating deployment");
  });

});
