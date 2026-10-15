// Base URL (from project.yaml, resolved via playwright.config.ts): http://127.0.0.1:8765
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.use({ baseURL: "http://127.0.0.1:8765" });

test.describe("Search \"weird\" `input` (M07_BS_003)", () => {

  test("quotes \" ' ` ${x} */ </script> \\ and ünïcödé ✓\nnew line @regression", async ({ action }) => {
    await test.step("1. Navigate to \"/search?q=\\\"a\\\"&b=`c`\"", async () => {
      await action.navigate("/search?q=\"a\"&b=`c`");
    });
    await test.step("2. Enter \"${process.exit(1)}\" into \"q\"", async () => {
      await action.enterText("q", "${process.exit(1)}");
    });
    await test.step("3. Enter <value> into \"q\"", async () => {
      await action.enterText("q", "'); DROP TABLE x; --");
    });
    await test.step("4. Verify \"results\" contains \"*/ alert(1) /*\" — line1\nline2\ttab \\u2028   sep", async () => {
      await action.verifyContainsText("results", "*/ alert(1) /*", "line1\nline2\ttab \\u2028   sep");
    });
  });

});
