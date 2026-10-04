// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Read customer success stories through story cards (M01_BS_004)", () => {

  test("positive — reading customer success stories through story cards succeeds @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("retail_adidas_drives_enterprise_wide");
    await action.verifyVisible("retail_adidas_drives_enterprise_wide", "Adidas customer story card should be visible in the Customer Story Cards section");
    await action.verifyVisible("retail_tapestry_amplifies_store_associate_voices", "Tapestry customer story card should be visible in the Customer Story Cards section");
    await action.click("retail_adidas_drives_enterprise_wide");
    await action.verifyUrlContains("/customer-stories/", "User should be navigated to a customer story detail page");
    await action.goBack();
    await action.click("retail_tapestry_amplifies_store_associate_voices");
    await action.verifyUrlContains("/customer-stories/", "User should be navigated to another customer story detail page");
    await action.goBack();
    await action.click("view_more_stories");
    await action.verifyUrlContains("/customer-stories/", "View more stories link should navigate to additional customer stories");
  });

});
