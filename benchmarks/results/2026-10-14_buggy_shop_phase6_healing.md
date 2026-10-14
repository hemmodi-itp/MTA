# Phase 6 healing benchmark — buggy_shop (2026-10-14)

Real Chromium + Playwright through UIExecutionAgent; triage + the healing tools the LLM loop calls (deterministic, no model). Ground truth: `data-bench-id` (never read by the fingerprint).

Clean build: 14 passed, 0 failed ['a description is shown as text, never run @smoke: Error: [locator_key=flash] expect(locator).toContainText(expected) failed\n\nLocator: getByTestId(\'flash\')\nExpected substring: "Product created"\nTimeout: 10000ms\nError: element(s) not found\n\nCall log:\n  - Expect "toContainText" getByTestId(\'flash\') with timeout 10000ms\n  - waiting for getByTestId(\'fla']; fingerprints recorded: 16.

| KPI | Result | Target |
|---|---|---|
| Heal success (LOC_01–10) | **9/10 (90.0%)** | ≥ 80% |
| Wrong-element heals | **0** | 0 |
| Controls refused (element replaced) | 2/2 | all |
| Seeded bugs detected | 10/10 | all |
| … classified product_defect | 10/10 | all |
| … failures sent to healing | **0** | 0 |

## Locator changes

| Change | Broken key | Triage | Outcome | Healed to (truth) |
|---|---|---|---|---|
| LOC_01 | login_button | flaky, test_defect.locator | healed | {'login_button': 'login_button'} |
| LOC_02 | username | flaky, test_defect.locator | healed | {'username': 'username'} |
| LOC_03 | password | flaky, test_defect.locator | healed | {'password': 'password'} |
| LOC_04 | save_product | test_defect.locator | not healed | {'save_product': 'save_product'} |
| LOC_05 | product_name | test_defect.locator | healed | {'product_name': 'product_name'} |
| LOC_06 | price | test_defect.locator | healed | {'price': 'price'} |
| LOC_07 | category | test_defect.locator | healed | {'category': 'category'} |
| LOC_08 | search | test_defect.locator | healed | {'search': 'search'} |
| LOC_09 | add_to_cart | test_defect.locator | healed | {'add_to_cart': 'add_to_cart'} |
| LOC_10 | help_link | test_defect.locator | healed | {'help_link': 'help_link'} |
| LOC_11 (control) | save_product | product_defect | refused | — |
| LOC_12 (control) | product_name | product_defect, test_defect.locator | refused | — |

## Seeded product bugs

| Bug | Failed tests | Verdicts | Healable |
|---|---|---|---|
| BUG_01 | 1 | product_defect | 0 |
| BUG_05 | 1 | product_defect | 0 |
| BUG_06 | 1 | product_defect | 0 |
| BUG_07 | 1 | product_defect | 0 |
| BUG_13 | 1 | product_defect | 0 |
| BUG_16 | 1 | product_defect | 0 |
| BUG_17 | 1 | product_defect | 0 |
| BUG_18 | 1 | product_defect | 0 |
| BUG_19 | 1 | product_defect | 0 |
| BUG_21 | 1 | product_defect | 0 |
