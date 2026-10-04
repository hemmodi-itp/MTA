# Test Scripts

This folder holds the executable Playwright test scripts produced by **ScriptGenerationAgent**. These are the final deliverable of Module 2 — runnable TypeScript files executed by `npx playwright test`. All files here are written by the pipeline — do not edit them manually (use HealingAgent to fix locator failures).

---

## Directory structure

Scripts are organized into four subdirectories by execution level:

```
test_scripts/
├── individual/               ← Level 1: one .spec.ts per scenario, for targeted runs
│   ├── test_SC-M01-001_login.spec.ts
│   └── test_SC-M02-001_dashboard_load.spec.ts
│
├── M01/                      ← Level 2: all M01 specs grouped, for module-level runs
│   └── test_SC-M01-001_login.spec.ts
│
├── M02/                      ← Level 2: all M02 specs grouped
│   └── test_SC-M02-001_dashboard_load.spec.ts
│
└── workflows/                ← Level 4: multi-step cross-module specs
    └── complete_flow.spec.ts
```

Level 3 (suite) execution reads from `individual/` — the suite JSON lists which scenario IDs to include.

---

## How to run

```bash
# Level 1 — single spec
python cli_appevolve.py test --level 1 --file test_SC-M01-001_login.spec.ts

# Level 2 — all specs in a module
python cli_appevolve.py test --level 2 --module M01

# Level 3 — named suite (reads test_suites/*.json)
python cli_appevolve.py test --level 3 --suite smoke
python cli_appevolve.py test --level 3 --suite regression
python cli_appevolve.py test --level 3 --suite module_01

# Level 4 — cross-module workflow
python cli_appevolve.py test --level 4 --workflow complete_flow

# Headed mode (visible browser) — append to any command
python cli_appevolve.py test --level 2 --module M01 --headed
```

---

## File naming

```
test_SC-{scenario_id}_{snake_case_title}.spec.ts
```

Examples:
- `test_SC-M01-001_successful_login.spec.ts`
- `test_SC-M02-003_dashboard_filter_by_status.spec.ts`

The `test_` prefix and `.spec.ts` extension are required for Playwright to auto-discover the file.

---

## Spec file format

Each `.spec.ts` file contains one `test.describe` block with 8-10 tests:
- **1 positive test** — the happy path through the scenario
- **≥4 negative tests** — empty fields, XSS, SQL injection, wrong format
- **≥3 boundary tests** — at-max-length, one-over-max, URL-as-input, unicode

```typescript
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://fallback.example.com';

test.describe('Successful Login (SC-M01-001)', () => {

  test('positive — valid credentials log in successfully', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.getByPlaceholder('Username').fill('testuser@example.com');
    await page.getByPlaceholder('Password').fill('ValidPass123!');
    await page.getByRole('button', { name: 'Log In' }).click();
    await expect(
      page,
      'After valid login, user must land on the dashboard URL'
    ).toHaveURL(/dashboard/);
  });

  test('negative — empty credentials show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.getByRole('button', { name: 'Log In' }).click();
    await expect(
      page.getByText('required'),
      'Validation error must appear when both fields are empty'
    ).toBeVisible();
  });

  // ... 6 more tests
});
```

---

## Locator priority order

ScriptGenerationAgent is instructed to use locators in this order (most stable → least stable):

```
1. page.getByPlaceholder("...")           ← semantic; most stable
2. page.getByRole("button", { name: "..." })  ← ARIA role; stable
3. page.getByText("...")                  ← visible text; stable
4. page.locator("[name='...']")           ← HTML attribute; moderate
5. page.locator("#id")                    ← element ID; moderate
6. page.locator("css")                    ← CSS selector; fragile — last resort
7. test.skip("no locator for: <desc>")   ← when no locator available; never times out
```

---

## Assertion rules

**Every `expect()` call must have a second string argument** describing what should be true and why it matters. This description appears in the Playwright HTML report as the failure reason.

```typescript
// ✓ CORRECT — failure reason is shown in the HTML report
await expect(element, 'Submit button must be enabled before the form is filled').toBeEnabled();

// ✗ WRONG — HTML report shows no failure reason
await expect(element).toBeEnabled();
```

---

## Maintained by HealingAgent

When DOM changes cause locator failures, HealingAgent rewrites **only the failing `test()` blocks** — it never rewrites an entire spec file. The spec file keeps the same name; only the broken blocks are patched. The `test_suite.json` is updated with status `"healed"`.
