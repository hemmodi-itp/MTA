// Base URL (from project.yaml, resolved via playwright.config.ts): http://127.0.0.1:8765
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ baseURL: "http://127.0.0.1:8765" });

test.describe("Create product (M03_BS_001)", () => {

  test("AC-03.3.1 price empty is rejected", { tag: ["@P0", "@negative", "@regression", "@REQ-03", "@AC-03.3.1", "@ep"], annotation: [{ type: "ac", description: "AC-03.3.1" }, { type: "tc", description: "M03_TC_005" }, { type: "case", description: "TC-a21f1f4b" }, { type: "scenario", description: "M03_BS_001" }] }, async ({ action }) => {
    await test.step("1. Navigate to \"/products/new\"", async () => {
      await action.navigate("/products/new");
    });
    await test.step("2. Enter ••• into \"password\"", async () => {
      await action.enterText("password", "s3cret!");
    });
    await test.step("3. Enter \"\" into \"price\"", async () => {
      await action.enterText("price", "");
    });
    await test.step("4. Click \"save_product_button\"", async () => {
      await action.click("save_product_button");
    });
    await test.step("5. Verify post request \"/products\" -> 4xx", async () => {
      await action.verifyRequest("POST", "/products", "4xx");
    });
    await test.step("6. Verify \"product_form_errors\" contains \"Price is required\" — Error message should state that price is required", async () => {
      await action.verifyContainsText("product_form_errors", "Price is required", "Error message should state that price is required");
    });
    await test.step("7. Verify no new console errors", async () => {
      await action.verifyNoNewConsoleErrors();
    });
  });

  test("AC-03.3.2 boundary price 0.01 is accepted", { tag: ["@P1", "@boundary", "@regression", "@REQ-03", "@AC-03.3.2", "@AC-03.1", "@bva"], annotation: [{ type: "ac", description: "AC-03.3.2" }, { type: "ac", description: "AC-03.1" }, { type: "tc", description: "M03_TC_006" }, { type: "case", description: "TC-0bd2" }, { type: "scenario", description: "M03_BS_001" }] }, async ({ action }) => {
    await test.step("1. Navigate to \"/products/new\"", async () => {
      await action.navigate("/products/new");
    });
    await test.step("2. Remember the count of \"product_rows\"", async () => {
      await action.rememberCount("product_rows");
    });
    await test.step("3. Enter \"0.01\" into \"price\"", async () => {
      await action.enterText("price", "0.01");
    });
    await test.step("4. Click \"save_product_button\"", async () => {
      await action.click("save_product_button");
    });
    await test.step("5. Reload and verify: Verify the count of \"product_rows\" changed by 1", async () => {
      await action.reload();
      await action.verifyCountChangedBy("product_rows", 1);
    });
    await test.step("6. Verify no new console errors", async () => {
      await action.verifyNoNewConsoleErrors();
    });
  });

});
