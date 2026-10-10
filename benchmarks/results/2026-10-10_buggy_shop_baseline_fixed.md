# Benchmark — buggy_shop — 2026-10-10

MTA commit `48ee84d` · label `baseline_fixed` · 53 tests executed of 53 generated

| KPI | Value |
|---|---|
| Requirement (AC) coverage | 0.0% (0/27) |
| **Seeded-bug detection rate** | **4.5%** (1/22 evaluated, 22 seeded) |
| False-failure rate (bug-free build) | 28.3% |
| Flaky rate (2 bug-free runs) | 0.0% |
| Heal precision | n/a (0 applied, 0 wrong) |
| Generation runtime | 2992.0 s |
| Total runtime | 7471.0 s |
| LLM calls / cache hits | 223 / 0 |
| LLM tokens in / out | 1,094,320 / 439,939 |
| LLM cost | unpriced |

> AC coverage note: no executed test links to an AC id (v1 artifacts carry no AC links)

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
| BUG_08 | accessibility | medium | AC-01.4 | yes | boundary — username field input exceeds , negative — authentication failure due to … | Accessibility scan (label / accessible name check) |
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

- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_001_successful_user_authentication.spec.ts::positive — user authenticates successfully with valid credentials and redirects to products page @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_003_unauthenticated_page_redirect_to_login_page.spec.ts::positive — unauthenticated user attempting to access protected page is redirected to login @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_004_user_logout_and_server_session_invalidation.spec.ts::positive — user logout invalidates session and redirects protected page access to login @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_create_a_product_successfully_with_duplicate_submission_prevention.spec.ts::positive — create a product successfully with duplicate submission prevention @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_003_prevent_order_submission_from_an_empty_cart.spec.ts::positive — attempting checkout with an empty cart prevents order submission and keeps user on cart page @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_008_invalidate_user_session_upon_explicit_logout.spec.ts::positive — explicit logout invalidates user session and redirects protected route access to login @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_upload_a_valid_csv_or_png_file.spec.ts::boundary — upload file exceeding size limit shows error @regression`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_upload_a_valid_csv_or_png_file.spec.ts::negative — upload unsupported file format shows error @regression`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_001_upload_a_valid_csv_or_png_file.spec.ts::positive — upload a valid CSV file succeeds @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_reject_invalid_file_type_or_oversized_file_uploads.spec.ts::boundary — upload valid CSV file exceeding 1 MB is rejected with error message @regression`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_reject_invalid_file_type_or_oversized_file_uploads.spec.ts::negative — upload unsupported PDF file is rejected with error message @regression`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_002_reject_invalid_file_type_or_oversized_file_uploads.spec.ts::positive — upload valid CSV file succeeds @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_006_invalidate_user_session_on_logout.spec.ts::positive — perform protected cart action before logout and verify session invalidation (cart cluster) @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_006_invalidate_user_session_on_logout.spec.ts::positive — perform protected products action before logout and verify session invalidation (products cluster) @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M05/test_M05_BS_006_invalidate_user_session_on_logout.spec.ts::positive — session is invalidated upon logging out (log cluster) @smoke`

## ACs with no linked executed test

AC-01.1, AC-01.2, AC-01.3, AC-01.4, AC-02.1, AC-02.2, AC-02.3, AC-02.4, AC-02.5, AC-02.6, AC-03.1, AC-03.2, AC-03.3, AC-03.4, AC-03.5, AC-03.6, AC-03.7, AC-04.1, AC-04.2, AC-05.1, AC-05.2, AC-05.3, AC-05.4, AC-06.1, AC-06.2, AC-07.1, AC-08.1
