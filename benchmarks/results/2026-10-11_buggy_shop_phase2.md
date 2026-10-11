# Benchmark — buggy_shop — 2026-10-11

MTA commit `3c39c3a` · label `phase2` · 74 tests executed of 74 generated

| KPI | Value |
|---|---|
| Requirement (AC) coverage | 77.8% (21/27) |
| AC coverage, direct links only | 77.8% (21/27) |
| **Seeded-bug detection rate** | **4.5%** (1/22 evaluated, 22 seeded) |
| False-failure rate (bug-free build) | 18.9% |
| Flaky rate (1 bug-free runs) | n/a |
| Heal precision | n/a (0 applied, 0 wrong) — not measured |
| Generation runtime | 2321.9 s |
| Total runtime | 5597.2 s |
| LLM calls / cache hits | 226 / 6 |
| LLM tokens in / out | 1,127,349 / 478,372 |
| LLM cost | unpriced |
| AC extraction recall (vs acs.yaml) | 100.0% |
| Deep discovery (Phase 2) | success in 40.4 s — 23 states, 10 forms, 29 probes, 14 endpoints |
| Element recall, link-reachable (vs elements.yaml) | 100.0% |
| Constraint capture | 100.0% |
| Page coverage (app_map) | 100.0% |
| Observed validation messages (vs validation_messages.yaml) | 100.0% |
| Discovery step per module (s) | M01 42.8, M02 57.3, M03 60.6, M04 46.9, M05 39.6, M06 42.0 |

> Cost not computed — no price in benchmarks/pricing.yaml for: gemini/gemini-3.6-flash

## Detection by category

| Category | Caught / enabled |
|---|---|
| accessibility | 1 / 1 |
| authorization_idor | 0 / 1 |
| authorization_role | 0 / 1 |
| business_rule | 0 / 1 |
| calculation | 0 / 1 |
| concurrency | 0 / 1 |
| error_handling | 0 / 1 |
| navigation | 0 / 1 |
| pagination | 0 / 1 |
| performance | 0 / 1 |
| persistence | 0 / 1 |
| required_validation | 0 / 1 |
| search | 0 / 1 |
| security_xss | 0 / 1 |
| server_client_mismatch | 0 / 1 |
| session | 0 / 1 |
| sorting | 0 / 1 |
| state_machine | 0 / 1 |
| upload_validation | 0 / 1 |
| validation_boundary | 0 / 1 |
| validation_numeric | 0 / 1 |
| wrong_message | 0 / 1 |

## Per bug

| Bug | Category | Severity | AC | Caught | By | How detectable |
|---|---|---|---|---|---|---|
| BUG_01 | validation_boundary | medium | AC-03.2 | no |  | UI boundary-value analysis (name of exactly 50 characters) |
| BUG_02 | server_client_mismatch | high | AC-03.3 | no |  | API only (POST /api/products with price -1) |
| BUG_03 | calculation | high | AC-05.2 | no |  | UI exact total assertion (1 x Gel Pen should total 1.01) |
| BUG_04 | authorization_idor | critical | AC-06.2 | no |  | Role / URL tampering (alice opens /orders/1) |
| BUG_05 | security_xss | critical | AC-03.5 | no |  | Security probe (script/img payload in description) |
| BUG_06 | navigation | low | AC-08.1 | no |  | Link check |
| BUG_07 | error_handling | high | AC-02.4 | no |  | Edge-case input (search for %) |
| BUG_08 | accessibility | medium | AC-01.4 | yes | AC-01.1 boundary — username exceeding ma, AC-01.1 negative — incorrect password su … | Accessibility scan (label / accessible name check) |
| BUG_09 | performance | medium | AC-02.6 | no |  | Timing budget (2 s) |
| BUG_10 | state_machine | high | AC-05.4 | no |  | Invalid state transition (checkout with empty cart) |
| BUG_11 | session | critical | AC-01.3 | no |  | Reuse old session cookie / back button after logout |
| BUG_12 | concurrency | medium | AC-03.6 | no |  | Double click / repeated submit |
| BUG_13 | wrong_message | medium | AC-01.2 | no |  | Exact error text assertion |
| BUG_14 | sorting | low | AC-02.3 | no |  | Order assertion on equal-price products |
| BUG_15 | pagination | medium | AC-02.5 | no |  | Filter then paginate |
| BUG_16 | authorization_role | critical | AC-07.1 | no |  | Role matrix (user opens /admin) |
| BUG_17 | upload_validation | high | AC-04.2 | no |  | Disallowed file type upload |
| BUG_18 | required_validation | medium | AC-03.1 | no |  | Negative equivalence partition (empty name) |
| BUG_19 | search | low | AC-02.2 | no |  | Equivalence partition on letter case |
| BUG_20 | persistence | high | AC-03.7 | no |  | Reload check after delete |
| BUG_21 | validation_numeric | high | AC-05.1 | no |  | Boundary-value analysis (quantity 0 / -1) |
| BUG_22 | business_rule | high | AC-05.3 | no |  | Repeat action (apply SAVE10 twice) |

## Tests failing on the bug-free build

- `bench_buggy_shop/test_creation/test_scripts/M02/test_M02_BS_004_filter_search_and_sort_retention_across_pagination.spec.ts::AC-02.5 positive — search button opens search controls`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_006_prevent_duplicate_product_submission_and_double_click.spec.ts::AC-03.6.1 positive — rapid submit disables save button and prevents duplicate product creation`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_004_prevent_checkout_with_empty_cart.spec.ts::AC-05.4.1 negative — empty cart check prevents navigating to checkout`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_004_prevent_checkout_with_empty_cart.spec.ts::AC-05.4.1 positive — checkout with empty cart is blocked and remains on cart page`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_upload_valid_csv_or_png_file_within_size_limit.spec.ts::AC-04.1 boundary — upload file exceeding 1 MB size limit fails`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_upload_valid_csv_or_png_file_within_size_limit.spec.ts::AC-04.1 negative — upload file with unsupported format fails`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_upload_valid_csv_or_png_file_within_size_limit.spec.ts::AC-04.1 positive — upload valid CSV file within size limit succeeds`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_reject_file_upload_with_unsupported_file_format.spec.ts::AC-04.2.1 boundary — reject file upload with unsupported TXT format and long filename`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_reject_file_upload_with_unsupported_file_format.spec.ts::AC-04.2.1 negative — reject file upload with unsupported PDF format`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_reject_file_upload_with_unsupported_file_format.spec.ts::AC-04.2.1 positive — valid file upload with CSV format`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_003_reject_file_upload_exceeding_maximum_size_limit.spec.ts::AC-04.2.2 boundary — reject file upload slightly exceeding 1 MB limit boundary`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_003_reject_file_upload_exceeding_maximum_size_limit.spec.ts::AC-04.2.2 negative — reject file upload exceeding 1 MB size limit`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_003_reject_file_upload_exceeding_maximum_size_limit.spec.ts::AC-04.2.2 positive — upload valid file under 1 MB limit succeeds`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_006_invalidate_user_session_upon_logout.spec.ts::AC-03.1.1 positive — session is invalidated upon logout and subsequent access to protected route redirects to login`

## ACs with no linked executed test

AC-02.2, AC-02.3, AC-02.4, AC-03.7, AC-05.1, AC-05.2

> Heal probe disabled (--no-healing).
