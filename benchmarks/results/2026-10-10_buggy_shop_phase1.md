# Benchmark — buggy_shop — 2026-10-10

MTA commit `2bf04b6` · label `phase1` · 67 tests executed of 67 generated

| KPI | Value |
|---|---|
| Requirement (AC) coverage | 85.2% (23/27) |
| AC coverage, direct links only | 85.2% (23/27) |
| **Seeded-bug detection rate** | **4.5%** (1/22 evaluated, 22 seeded) |
| False-failure rate (bug-free build) | 22.4% |
| Flaky rate (2 bug-free runs) | 0.0% |
| Heal precision | n/a (0 applied, 0 wrong) |
| Generation runtime | 2636.4 s |
| Total runtime | 7598.0 s |
| LLM calls / cache hits | 228 / 0 |
| LLM tokens in / out | 1,240,952 / 491,623 |
| LLM cost | unpriced |
| AC extraction recall (vs acs.yaml) | 100.0% |

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
| BUG_08 | accessibility | medium | AC-01.4 | yes | AC-01.1 positive — user authenticates su, AC-01.2.1 boundary — password exceeding  … | Accessibility scan (label / accessible name check) |
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

- `bench_buggy_shop/test_creation/test_scripts/M02/test_M02_BS_010_session_invalidation_on_user_logout.spec.ts::AC-01.3 positive — user logout invalidates session and redirects protected page access to login`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_003_prevention_of_duplicate_product_creation_on_rapid_submission.spec.ts::AC-03.6.2 positive — rapid double-click on save button disables button and prevents duplicate product creation`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_002_cart_pricing_calculations_and_half_up_rounding.spec.ts::AC-05.3.1 negative — apply invalid discount code`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_005_successful_order_placement_and_cart_clearing.spec.ts::AC-06.1.1 positive — proceed to checkout from non-empty cart to complete order placement`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_successful_upload_of_valid_csv_or_png_file.spec.ts::AC-04.1 boundary — uploading a file exceeding max size limit displays error message`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_successful_upload_of_valid_csv_or_png_file.spec.ts::AC-04.1 negative — uploading an unsupported file format displays error message`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_successful_upload_of_valid_csv_or_png_file.spec.ts::AC-04.1 positive — uploading a valid CSV file succeeds`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_rejection_of_unsupported_file_formats_during_upload.spec.ts::AC-04.2.1 boundary — rejection of unsupported file format (.pdf) with maximum filename length`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_rejection_of_unsupported_file_formats_during_upload.spec.ts::AC-04.2.1 negative — rejection of unsupported executable file format (.exe)`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_rejection_of_unsupported_file_formats_during_upload.spec.ts::AC-04.2.1 positive — valid CSV file upload succeeds`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_003_rejection_of_file_upload_exceeding_size_limit.spec.ts::AC-04.2.2 boundary — uploading a file at the exact 1 MB limit is accepted`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_003_rejection_of_file_upload_exceeding_size_limit.spec.ts::AC-04.2.2 negative — uploading a file exceeding 1 MB displays size limit error`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_003_rejection_of_file_upload_exceeding_size_limit.spec.ts::AC-04.2.2 positive — upload valid file within size limit succeeds`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_008_session_invalidation_on_user_logout.spec.ts::AC-01.3 positive — attempting to navigate to products page after logout redirects to login`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_008_session_invalidation_on_user_logout.spec.ts::AC-01.3 positive — user session is invalidated on logout and protected endpoint redirects to login`

## ACs with no linked executed test

AC-02.2, AC-02.4, AC-03.7, AC-05.1
