// Base URL (from project.yaml, resolved via playwright.config.ts): http://127.0.0.1:8765
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';
import * as flows from '../../flows.generated';

test.use({ baseURL: "http://127.0.0.1:8765" });

test.describe("Checkout (M05_BS_002)", () => {

  test("checkout via flow @smoke", async ({ action }) => {
    await flows.login(action, "alice", "alice-pass-1");
    await flows.addToCart(action, "3");
    await action.verifyContainsText("cart_count", "1");
  });

});
