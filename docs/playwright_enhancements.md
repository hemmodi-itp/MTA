# Playwright Enhancements

## Current Capabilities

### Browser & Execution
- `sync_playwright()` + `chromium.launch()` — Python-side DOM scanning
- `npx playwright test` — TypeScript test runner (primary execution path)
- Two browser projects: `chromium` (headless), `chromium-headed`
- Retries: 2 on CI, 1 local; Workers: 1 on CI, 2 local

### Locator Strategies (priority order in ScriptGenerationAgent)
1. `getByPlaceholder()`
2. `getByRole(role, { name })`
3. `getByText()`
4. `getByLabel()`
5. `getByTestId()`
6. `locator('[name="..."]')`
7. `locator('#id')`
8. `locator('css')` — last resort

### Interactions
- `page.fill()`, `page.click()`, `page.press()`, `page.select_option()`
- `locator.first()`, `locator.nth()`, `locator.count()`
- `page.goto()` with `wait_until: "networkidle"`
- `page.evaluate()` for JS execution
- `page.route()` / `page.unrouteAll()` — imported but minimally used

### Assertions
`toBeVisible()`, `toHaveValue()`, `toHaveText()`, `toHaveURL()`, `toHaveCount()`, `toContainText()`, `toHaveTitle()`, `toBeLessThan()` — all with required description strings

### Test Structure
- `test.describe()` with `mode: 'serial'` for stateful flows
- `beforeAll` / `afterAll` / `beforeEach` / `afterEach` hooks
- `test.skip()` as fallback when locator unavailable

### Reporters
- JSON (machine-readable, feeds the pipeline)
- HTML (interactive with traces)
- List (console streaming)
- Screenshots on failure, video on first retry, trace on first retry — configured but not surfaced in the reporting layer

### DOM Scanner (Python)
- `element_handle.get_attribute()`, `inner_text()`, `is_visible()`, `is_enabled()`
- CSS selector + XPath generation
- Label association via `evaluate()`

---

## Proposed Enhancements

### Tier 1 — High Impact, Low Integration Cost

**1. Soft Assertions (`expect.soft()`)**
Currently any failed `expect()` stops the test. Soft assertions collect all failures and report them together — better for form validation scenarios.
```ts
await expect.soft(locator, 'email field visible').toBeVisible();
await expect.soft(locator, 'submit enabled').toBeEnabled();
```
Where to add: ScriptGenerationAgent prompt — change assertion type for non-critical checks.

**2. Console & Error Monitoring**
Currently blind to JS errors thrown during test execution. A listener in `beforeEach` catches unhandled exceptions and uncaught promise rejections.
```ts
const errors: string[] = [];
page.on('pageerror', err => errors.push(err.message));
// assert at end of test:
expect(errors, 'no JS errors on page').toHaveLength(0);
```
Where to add: ScriptGenerationAgent prompt — inject into `beforeEach` block.

**3. `storageState` — Auth State Reuse**
Every test currently navigates and re-authenticates from scratch. Saving auth state once and reusing it across all tests reduces run time significantly for apps behind login.
```ts
// globalSetup.ts
await page.context().storageState({ path: 'auth.json' });
// playwright.config.ts
use: { storageState: 'auth.json' }
```
Where to add: `playwright.config.ts` + new `globalSetup.ts`; OrchestratorAgent to detect auth scenarios.

**4. Test Tags & Annotations**
No way to run a subset of tests (e.g., smoke only) right now. Tags enable selective CI execution.
```ts
test('positive — login succeeds @smoke @critical', ...)
```
Run with: `npx playwright test --grep @smoke`
Where to add: ScriptGenerationAgent prompt — tag tests based on scenario priority from `business_scenarios.json`.

---

### Tier 2 — Medium Effort, Strong Resilience Gain

**5. Network Interception for Negative Tests**
`page.route()` is already imported. Use it to simulate real failure conditions instead of only bad input values.
```ts
await page.route('**/api/**', route => route.abort());             // network failure
await page.route('**/api/**', route => route.fulfill({ status: 500 })); // server error
await page.route('**/api/**', async route => {
  await new Promise(r => setTimeout(r, 10000));
  await route.continue();                                           // timeout simulation
});
```
Where to add: ScriptGenerationAgent — generate route-based negative test variants in addition to input-based ones.

**6. Multi-Browser Coverage (Firefox + WebKit)**
Currently Chromium-only. Add Firefox and WebKit to `playwright.config.ts`.
```ts
projects: [
  { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  { name: 'firefox',  use: { ...devices['Desktop Firefox'] } },
  { name: 'webkit',   use: { ...devices['Desktop Safari'] } },
]
```
Where to add: `playwright.config.ts`; UIExecutionAgent to pass `--project` flag per run mode.

**7. Mobile Device Emulation**
No mobile testing currently. Playwright ships 50+ device profiles. ScriptGenerationAgent can generate a mobile variant per scenario.
```ts
use: { ...devices['iPhone 15'] }  // or 'Pixel 7'
```
Where to add: `playwright.config.ts` mobile project entries; orchestrator flag `--mobile`.

**8. File Upload (`page.setInputFiles()`)**
DOM scanner records file inputs but the script generator doesn't handle them. Needed for any app with document upload flows.
```ts
await page.setInputFiles('input[type="file"]', 'path/to/file.pdf');
```
Where to add: ScriptGenerationAgent prompt — detect `type="file"` elements in `scenario_element_map.json`.

**9. Dialog Handling (`page.on('dialog')`)**
Tests silently hang if a browser `alert()`, `confirm()`, or `prompt()` is triggered and no handler is registered.
```ts
page.on('dialog', dialog => dialog.accept());
```
Where to add: ScriptGenerationAgent — inject into `beforeEach` as a default safety net.

**10. `page.clock` for Time-Dependent Tests**
For countdown timers, session expiry, scheduled events — advance time without actually waiting.
```ts
await page.clock.setSystemTime(new Date('2026-12-31'));
await page.clock.tick(60_000); // advance 1 minute instantly
```
Requires Playwright 1.45+. Directly applicable to the existing "lightning deal countdown" scenario in AmazonTest.
Where to add: ScriptGenerationAgent — detect time-dependent scenarios from `business_scenarios.json`.

---

### Tier 3 — Architecture-Level Enhancements

**11. API Testing via `request` Context**
Playwright's `request` fixture makes HTTP calls in the same session with the same auth cookies. Breaks the UI-only limitation.
```ts
const response = await request.get('/api/products?q=laptop');
await expect(response).toBeOK();
const body = await response.json();
expect(body.items.length).toBeGreaterThan(0);
```
Where to add: New `api_test_creation` module; ScriptGenerationAgent variant for API scenarios detected in BRD.

**12. HAR Recording for DOM Drift Detection**
Record all network traffic as HAR during a run; diff against previous HAR to detect API contract changes before tests break.
```ts
await context.routeFromHAR('recorded.har', { update: true });
```
Where to add: UIExecutionAgent — record HAR on each run; new `tools/discovery/har_diff.py` for drift comparison.

**13. Visual Regression (`toMatchSnapshot()` / `toBeScreenshot()`)**
Config has `screenshot: 'only-on-failure'` but no baseline comparisons are generated. Snapshot assertions catch visual regressions functional assertions miss.
```ts
await expect(page).toHaveScreenshot('product-page.png', { maxDiffPixels: 100 });
```
Where to add: ScriptGenerationAgent — add one snapshot assertion per scenario's happy path test.

**14. Accessibility Snapshot (`page.accessibility.snapshot()`)**
Generates a full accessibility tree. Validates ARIA roles match what the DOM scanner detected; catches missing labels and broken roles.
Where to add: DiscoveryAgent / DOM scanner — run alongside element scan; feed ComprehensionAgent as additional context.

**15. JS Coverage API (`page.coverage`)**
Chromium-only. Tracks which app JS/CSS lines were exercised during tests — "code coverage from the outside."
Where to add: UIExecutionAgent — collect and write coverage JSON alongside Playwright JSON report; ReportingAgent to surface coverage %.

---

## Priority Order

| # | Capability | Effort | Resilience Gain |
|---|-----------|--------|-----------------|
| 1 | Soft assertions | Low | Richer failure reports |
| 2 | Console/pageerror monitoring | Low | Catches silent JS crashes |
| 3 | `storageState` auth reuse | Low | Faster, stable test runs |
| 4 | Test tags (`@smoke`, `@critical`) | Low | Selective CI execution |
| 5 | Network interception for negatives | Medium | Real failure-path testing |
| 6 | Dialog handling | Low | Prevents hangs on alerts |
| 7 | `page.clock` for time-dependent tests | Medium | Eliminates timing flakiness |
| 8 | File upload (`setInputFiles`) | Medium | Covers upload flows |
| 9 | Multi-browser (Firefox + WebKit) | Medium | Cross-browser confidence |
| 10 | Mobile device emulation | Medium | Mobile coverage |
| 11 | API testing via `request` | High | Breaks UI-only limitation |
| 12 | Visual regression snapshots | Medium | Visual change detection |
| 13 | HAR recording for drift detection | High | Proactive DOM drift alerts |
| 14 | Accessibility snapshot | Medium | A11y validation |
| 15 | Coverage API | High | Test depth measurement |
