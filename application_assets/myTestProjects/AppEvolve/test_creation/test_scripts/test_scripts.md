# Test Scripts

This folder holds the executable Playwright test scripts produced by **ScriptGenerationAgent**. These are the final deliverable of Module 2 — runnable TypeScript files executed by `npx playwright test`.

## File naming

```
test_BS-{scenario_id}_{snake_case_title}.spec.ts
```

Examples:
- `test_BS-007_search_for_specific_products.spec.ts`
- `test_BS-012_submit_contact_form.spec.ts`

The `test_` prefix and `.spec.ts` extension are required for Playwright to auto-discover the file.

## What belongs here

One `.spec.ts` file per business scenario. Each file contains:

- **1 positive test** — the happy path through the scenario
- **≥4 negative tests** — empty fields, XSS, SQL injection, wrong format, no results
- **≥3 boundary tests** — at-max-length, one-over-max, URL-as-input, unicode

Total: **8–10 tests per spec**.

## TypeScript format

```typescript
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://fallback.example.com';

test.describe('Scenario Title (BS-007)', () => {

  test('positive — valid search term returns products', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(
      page.getByPlaceholder('Search Products ...'),
      'Search input must be present on the page'     // ← REQUIRED: describe the expected state
    ).toBeVisible();
    await page.getByPlaceholder('Search Products ...').fill('Flow Meter');
    await page.getByPlaceholder('Search Products ...').press('Enter');
    await expect(
      page.locator('.product'),
      'At least 1 product must appear after a valid search'
    ).toHaveCount({ min: 1 });
  });

  test('negative — empty search does not crash page', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.getByPlaceholder('Search Products ...').fill('');
    await page.getByPlaceholder('Search Products ...').press('Enter');
    await expect(
      page,
      'Page must not navigate away on empty search'
    ).not.toHaveURL('about:blank');
  });

});
```

## Locator rules (priority order)

1. `page.getByPlaceholder("...")` — semantic; most stable
2. `page.getByRole("button", { name: "..." })` — ARIA role; stable
3. `page.getByText("...")` — visible text; stable
4. `page.locator("[name='...']")` — attribute; moderate
5. `page.locator("#id")` — id; moderate
6. `page.locator("css")` — last resort; fragile positional CSS
7. `test.skip("no locator for: <description>")` — when no locator is available; never time out

## Assertion rules

**Every `expect()` call must have a second string argument** that describes, in plain English, what should be true and why it matters. This string appears in the Playwright HTML report as the failure reason.

```typescript
// ✓ CORRECT
await expect(element, 'Button must be enabled before submitting the form').toBeEnabled();

// ✗ WRONG — no failure reason in HTML report
await expect(element).toBeEnabled();
```

## Produced by

ScriptGenerationAgent reads:
- `test_creation/scenario_element_map.json` — which DOM elements are relevant per scenario
- `comprehension/business_scenarios.json` — what each scenario requires
- `test_creation/test_data/test_data.json` — 8-10 test variants per scenario
- `comprehension/interaction_catalog.json` — available UI interactions (reference only)

## Maintained by

**HealingAgent** monitors Playwright JSON results and rewrites individual `test('...', ...)` blocks when DOM changes cause locator failures. The spec file keeps the same name; only the failing blocks are updated. The suite manifest (`test_suite.json`) is updated with status `"healed"`.

## File types allowed

`.spec.ts` only. Configuration lives in `playwright.config.ts` at the project root. Shared fixtures go in `conftest.ts` (if needed).
