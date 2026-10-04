// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Navigate using navigation bar to fetch page information (M01_BS_001)", () => {

  test("positive — navigate to Products page via navigation bar successfully loads page information @smoke", async ({ action }) => {
    await action.navigate();
    await action.click("navigate_products_12");
    await action.verifyUrl("/products", "URL should contain /products after clicking Products navigation");
    await action.verifyContainsText("navigate_products_12", "AWS Products and Services", "Page heading should display AWS Products and Services");
    await action.verifyContainsText("navigate_products_12", "Explore our comprehensive cloud computing services", "Page content should contain service exploration text");
    await action.verifyCount("navigate_products_12", 5, "At least 5 service cards should be visible on the products page");
  });

  test("negative — navigation to Products page fails when page heading does not load @regression", async ({ action }) => {
    await action.navigate();
    await action.click("navigate_products_12");
    await action.verifyUrl("/products", "URL should contain /products after clicking Products navigation");
    await action.verifyText("navigate_products_12", "", "Page heading should be empty indicating failed load");
  });

});
