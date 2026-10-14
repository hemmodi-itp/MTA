# Phase 6 healing benchmark — buggy_shop (2026-10-14)

Real Chromium + Playwright through UIExecutionAgent; triage + the healing tools the LLM loop calls (deterministic, no model). Ground truth: `data-bench-id` (never read by the fingerprint).

Clean build: 15 passed, 0 failed ; fingerprints recorded: 16.

| KPI | Result | Target |
|---|---|---|
| Heal success (LOC_01–10) | **1/1 (100.0%)** | ≥ 80% |
| Wrong-element heals | **0** | 0 |
| Controls refused (element replaced) | 0/0 | all |
| Seeded bugs detected | 2/2 | all |
| … classified product_defect | 2/2 | all |
| … failures sent to healing | **0** | 0 |

## Locator changes

| Change | Broken key | Triage | Outcome | Healed to (truth) |
|---|---|---|---|---|
| LOC_04 | save_product | test_defect.locator | healed | {'save_product': 'save_product'} |

## Seeded product bugs

| Bug | Failed tests | Verdicts | Healable |
|---|---|---|---|
| BUG_01 | 1 | product_defect | 0 |
| BUG_05 | 1 | product_defect | 0 |
