# Test Scripts

This folder holds the executable Playwright test scripts produced by **ScriptGenerationAgent** — the final deliverable of test creation, runnable via `npx playwright test` (or, normally, via `python main.py`, which drives that for you). All files here are written by the pipeline — do not edit them manually; use HealingAgent (runs automatically after execution) to fix locator failures, or delete the spec and re-run generation for anything bigger.

---

## Directory structure

```
test_scripts/
├── test_SC-001_some_module_less_scenario.spec.ts   ← scenarios with no module_id sit flat here
│
├── M01/                       ← every M01 spec, grouped
│   └── test_M01_BS_001_login.spec.ts
│
└── M02/                       ← every M02 spec, grouped
    └── test_M02_BS_001_dashboard_load.spec.ts
```

There is no `individual/` or `workflows/` subdirectory — every scenario gets exactly one `.spec.ts`,
placed flat if it has no `module_id`, or under its module's directory if it does.

---

## How to run

```bash
# Full pipeline (discovery → ... → ui_execution → healing → reporting) for one module
python main.py --project YourProjectName --module M01

# Re-run execution only — no regeneration — e.g. after a manual edit or to retry flaky failures
python main.py --project YourProjectName --module M01 --force-execute

# Every module in one run
python main.py --project YourProjectName

# A named suite (test_suites/*.json) — can span multiple modules in one run
python main.py --project YourProjectName --suite smoke

# Headed vs headless is set per-project in project.yaml (`headless: true|false`), not per-command.
```

`ui_execution` invokes `npx playwright test` under the hood — you generally don't need to call it
directly, but you can (`npx playwright test test_creation/test_scripts/M01 --config playwright.config.ts`)
for a quick local check without going through the full pipeline.

---

## File naming

```
test_{scenario_id}_{snake_case_title}.spec.ts
```

`scenario_id` is whatever `business_scenarios.json` assigned — legacy hyphenated (`BS-001`, `SC-001`)
or the current module-scoped form (`M01_BS_001`). Both are valid and handled identically everywhere
downstream.

Examples:
- `test_M01_BS_001_successful_login.spec.ts`
- `test_M02_BS_003_dashboard_filter_by_status.spec.ts`

The `test_` prefix and `.spec.ts` extension are required for Playwright to auto-discover the file.

---

## Spec file format

Every test in a spec shares **one browser page**, launched once in `beforeAll` and closed once in
`afterAll` — not a fresh page per `test()`. This matters for modules with a `setup:` login sequence:
the login only needs to happen once per spec file, not once per test.

```typescript
import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://yourapp.com/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Successful Login (M01_BS_001)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    // A module's `setup:` steps (see project.yaml) are injected right here,
    // before any test runs — e.g. a login sequence.
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — valid credentials log in successfully', async () => {
    await page.goto(BASE_URL);
    await page.getByPlaceholder('Username').fill('testuser@example.com');
    await page.getByPlaceholder('Password').fill('ValidPass123!');
    await page.getByRole('button', { name: 'Log In' }).click();
    await expect(
      page,
      'After valid login, user must land on the dashboard URL'
    ).toHaveURL(/dashboard/);
  });

  test('negative — empty credentials show validation error', async () => {
    await page.goto(BASE_URL);
    await page.getByRole('button', { name: 'Log In' }).click();
    await expect(
      page.getByText('required'),
      'Validation error must appear when both fields are empty'
    ).toBeVisible();
  });

  // Optionally: one 'boundary — ...' test, per project.yaml's test_generation
  // config (max_negative_cases / max_boundary_cases — default 1 each).
});
```

Note: `test()` callbacks take **no fixture parameters** (`async () => {`, never `async ({ page }) =>
{`) — they reference the outer `page` declared above. This is a hard requirement of the generation
prompt, not a style preference; a spec that opens its own page per test breaks the shared-login model
setup steps depend on.

---

## Locator priority order

ScriptGenerationAgent is instructed to use locators in this order (most stable → least stable), and
must copy the exact `playwright_expr` from `scenario_element_map.json` verbatim — never invent one:

```
1. page.getByPlaceholder("...")               ← semantic; most stable
2. page.getByRole("button", { name: "..." })  ← ARIA role; stable
3. page.getByText("...")                      ← visible text; stable
4. page.locator("[name='...']")               ← HTML attribute; moderate
5. page.locator("#id")                        ← element ID; moderate
6. page.locator("css")                        ← CSS selector; fragile — last resort
7. test.skip("no locator for: <desc>")        ← when no locator is available
```

**This is now enforced, not just requested.** Every generated spec is checked statically and then
live-dry-run against the real page before it's trusted — see "Live locator validation" in
`test_creation/artifacts.md`. A spec that fails validation gets one retry, then falls back to a
deterministic generator rather than being written as-is.

---

## Assertion rules

**Every `expect()` call must have a second string argument** describing what should be true and why it matters. This description appears in the Playwright HTML report as the failure reason.

```typescript
// ✓ CORRECT — failure reason is shown in the HTML report
await expect(element, 'Submit button must be enabled before the form is filled').toBeEnabled();

// ✗ WRONG — HTML report shows no failure reason
await expect(element).toBeEnabled();
```

Assertions are also locator-constrained — ScriptGenerationAgent will not invent a heading or
`data-testid` selector just because a step implies one should exist. If nothing grounded is available
to assert, the step is either checked via `toHaveURL(...)` (no selector needed) or omitted.

---

## Maintained by HealingAgent

HealingAgent **runs automatically after every execution step**, as part of the full pipeline — it's
not an opt-in extra you trigger separately. When a test fails, it classifies the root cause first:
real app/network/auth failures are left alone (not locator problems, healing can't fix them); stale-
locator failures get a block-level patch. HealingAgent rewrites **only the failing `test()` blocks** —
it never rewrites an entire spec file, and the spec file keeps the same name. `test_suite.json` is
updated with status `"healed"` (LLM-patched) or `"healed_fallback"` (CSS-based fallback patch).
