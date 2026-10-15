// Base URL (from project.yaml, resolved via playwright.config.ts): http://127.0.0.1:8765
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ baseURL: "http://127.0.0.1:8765" });

test.describe("Action catalogue (M09_BS_001)", () => {

  test("every action renders @smoke", async ({ action }) => {
    await action.navigate("/x");
    await action.click("k");
    await action.doubleClick("k");
    await action.hover("k");
    await action.enterText("k", "v");
    await action.clearAndEnterText("k", "v");
    await action.pressKey(null, "Enter");
    await action.pressKey("k", "Tab");
    await action.checkCheckbox("k");
    await action.uncheckCheckbox("k");
    await action.selectDropdownByText("k", "Books");
    await action.selectDropdownByValue("k", "books");
    await action.scrollIntoView("k");
    await action.waitForElement("k", "visible");
    await action.waitForTimeout(250);
    await action.uploadFile("k", "fixtures/a.png");
    await action.verifyVisible("k");
    await action.verifyHidden("k", "m");
    await action.verifyText("k", "t");
    await action.verifyContainsText("k", "t", undefined, { soft: true });
    await action.verifyValue("k", "v", "m");
    await action.verifyEnabled("k");
    await action.verifyDisabled("k");
    await action.verifyBusyWhileSubmitting("k", "disabled while saving");
    await action.verifyChecked("k", undefined, { soft: true });
    await action.verifyCount("k", 3);
    await action.verifyUrl("/x");
    await action.verifyUrlContains("x");
    await action.verifyTitle("T");
    await action.verifyTitleContains("T");
    await action.verifyNoPageErrors();
    await action.takeScreenshot("shot");
    await action.goBack();
    await action.reload();
    await action.verifyRequest("POST", "/api/x", 201, undefined, "ok");
    await action.verifyNoRequest("DELETE", "/api/x", "m");
    await action.verifyFieldInvalid("k");
    await action.verifyNoDialog();
    await action.verifyNotInjected("mta-marker-1");
    await action.verifyNoNewConsoleErrors("m");
    await action.verifyValidationMessage("k", "Please fill out this field.");
    await action.verifyAriaSnapshot("k", "- heading \"Shop\"");
    await action.rememberCount("k");
    await action.verifyCountChangedBy("k", -1);
    await action.verifyDownload("k", "\\.csv$", 10);
    await action.verifyNewTab("k", "/help");
    await action.verifyStorage("cookie", "session", "httpOnly");
    await action.verifyResponseSchema("/api/products", {"type": "array"});
    await action.verifyApiState("GET", "/api/products/1", {"status": 200, "path": "name", "equals": "X"});
    await action.mockRoute("**/api/slow", {"status": 503, "delayMs": 100});
    await action.setOffline(true);
    await action.setClock("2026-01-01T00:00:00Z");
    await action.dragAndDrop("a", "b");
  });

});
