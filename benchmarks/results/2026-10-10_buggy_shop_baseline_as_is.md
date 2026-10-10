# Benchmark — buggy_shop — 2026-10-10

MTA commit `48ee84d` · label `baseline_as_is` · 40 tests executed of 40 generated

| KPI | Value |
|---|---|
| Requirement (AC) coverage | 0.0% (0/27) |
| **Seeded-bug detection rate** | **0.0%** (0/22 evaluated, 22 seeded) |
| False-failure rate (bug-free build) | 70.0% |
| Flaky rate (2 bug-free runs) | 0.0% |
| Heal precision | n/a (0 applied, 0 wrong) |
| Generation runtime | 2493.5 s |
| Total runtime | 5270.5 s |
| LLM calls / cache hits | 203 / 0 |
| LLM tokens in / out | 960,853 / 497,276 |
| LLM cost | unpriced |

> AC coverage note: no executed test links to an AC id (v1 artifacts carry no AC links)

> Cost not computed — no price in benchmarks/pricing.yaml for: gemini/gemini-3.6-flash

## Detection by category

| Category | Caught / enabled |
|---|---|
| accessibility | 0 / 1 |
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
| BUG_08 | accessibility | medium | AC-01.4 | no |  | Accessibility scan (label / accessible name check) |
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

- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_002_user_authentication_failure_with_invalid_credentials.spec.ts::boundary — user authentication fails with username exceeding character limit @regression`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_002_user_authentication_failure_with_invalid_credentials.spec.ts::negative — user authentication fails with incorrect password @regression`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_002_user_authentication_failure_with_invalid_credentials.spec.ts::positive — standard user authentication with valid credentials @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_003_successful_user_login_and_landing_page_navigation.spec.ts::boundary — login with username exceeding character limit remains on login page @regression`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_003_successful_user_login_and_landing_page_navigation.spec.ts::negative — login with invalid credentials fails and remains on login page @regression`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_003_successful_user_login_and_landing_page_navigation.spec.ts::positive — successful user login navigates to products page @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_004_user_logout_and_server_side_session_invalidation.spec.ts::positive — user logout invalidates session and redirects protected resource access to login @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_005_customer_order_visibility_restriction.spec.ts::negative — customer is denied access when attempting to view another customer's order @regression`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_005_customer_order_visibility_restriction.spec.ts::positive — customer can view their own order details @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_006_administrator_system_and_order_access.spec.ts::positive — administrator accesses admin orders page @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_007_json_api_authentication_safeguards.spec.ts::negative — unauthenticated requests to protected endpoints are guarded against HTTP 200 access @regression`
- `bench_buggy_shop/test_creation/test_scripts/M01/test_M01_BS_007_json_api_authentication_safeguards.spec.ts::positive — unauthenticated access to health check endpoint succeeds and protected endpoints are queried @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M02/test_M02_BS_001_browse_filter_sort_and_paginate_product_list.spec.ts::positive — navigate to products page @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M02/test_M02_BS_001_browse_filter_sort_and_paginate_product_list.spec.ts::positive — open search interface using search control @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_successfully_create_a_new_product_via_ui_form.spec.ts::boundary — product name exceeding maximum allowed length shows validation failure @regression`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_successfully_create_a_new_product_via_ui_form.spec.ts::negative — creating a product with missing name fails validation @regression`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_successfully_create_a_new_product_via_ui_form.spec.ts::positive — successfully create a new product via UI form @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_002_validate_product_form_input_fields_and_display_accessible_error_messages.spec.ts::boundary — product name and description exceeding character limits fail validation @regression`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_002_validate_product_form_input_fields_and_display_accessible_error_messages.spec.ts::negative — submitting product form with empty name and negative price fails validation @regression`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_002_validate_product_form_input_fields_and_display_accessible_error_messages.spec.ts::positive — valid product form submission succeeds @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_003_prevent_duplicate_product_creation_on_rapid_submissions.spec.ts::boundary — product creation with product name at maximum length disables save button on submit @regression`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_003_prevent_duplicate_product_creation_on_rapid_submissions.spec.ts::negative — product creation fails when mandatory product name is missing @regression`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_003_prevent_duplicate_product_creation_on_rapid_submissions.spec.ts::positive — rapid submission disables save button to prevent duplicate creation @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_002_applying_discount_codes_and_calculating_totals.spec.ts::boundary — discount code exceeding field character limit @regression`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_002_applying_discount_codes_and_calculating_totals.spec.ts::negative — apply unrecognized discount code UNKNOWN10 @regression`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_002_applying_discount_codes_and_calculating_totals.spec.ts::positive — apply discount code SAVE10 to cart and attempt re-application @smoke`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_006_administrator_access_to_all_customer_orders.spec.ts::negative — administrator accessing a non-existent order ID receives error state @regression`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_006_administrator_access_to_all_customer_orders.spec.ts::positive — administrator can access customer order details @smoke`

## ACs with no linked executed test

AC-01.1, AC-01.2, AC-01.3, AC-01.4, AC-02.1, AC-02.2, AC-02.3, AC-02.4, AC-02.5, AC-02.6, AC-03.1, AC-03.2, AC-03.3, AC-03.4, AC-03.5, AC-03.6, AC-03.7, AC-04.1, AC-04.2, AC-05.1, AC-05.2, AC-05.3, AC-05.4, AC-06.1, AC-06.2, AC-07.1, AC-08.1

> Heal probe not run: no bug was caught, so there was nothing a heal could hide.
