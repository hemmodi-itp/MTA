# Benchmark — buggy_shop — 2026-10-12

MTA commit `e96b03d` · label `phase4b_after` · 61 tests executed of 61 generated

| KPI | Value |
|---|---|
| Requirement (AC) coverage | 25.9% (7/27) |
| AC coverage, direct links only | 25.9% (7/27) |
| **Seeded-bug detection rate** | **100.0%** (3/3 evaluated, 22 seeded) |
| False-failure rate (bug-free build) | 18.0% |
| Flaky rate (2 bug-free runs) | 1.6% |
| Heal precision | n/a (0 applied, 0 wrong) — not measured |
| Generation runtime | n/a s |
| Total runtime | 1720.5 s |
| LLM calls / cache hits | 0 / 0 |
| LLM tokens in / out | 0 / 0 |
| LLM cost | $0.0000 |
| AC extraction recall (vs acs.yaml) | 63.0% |
| Test design (Phase 3, profile standard) | 111 cases selected of 394 generated, 32 cut; budget respected (est. 17.18 min) |
| Design AC coverage: any technique / excl. use_case / implemented in specs | 100.0% / 35.9% / 41.0% |
| Validation + state-machine bugs targeted: any / excl. use_case / implemented | 4 / 3 / 3 of 5 |
| All seeded bugs targeted by design (any / implemented) | 13 / 6 of 22 |

## Detection by category

| Category | Caught / enabled |
|---|---|
| required_validation | 1 / 1 |
| validation_boundary | 1 / 1 |
| validation_numeric | 1 / 1 |

## Per bug

| Bug | Category | Severity | AC | Caught | By | How detectable |
|---|---|---|---|---|---|---|
| BUG_01 | validation_boundary | medium | AC-03.2 | yes | AC-03.1.1 main flow: Name is required., AC-03.2.1 Name length max (50 chars) is  … | UI boundary-value analysis (name of exactly 50 characters) |
| BUG_02 | server_client_mismatch | high | AC-03.3 | not run |  | API only (POST /api/products with price -1) |
| BUG_03 | calculation | high | AC-05.2 | not run |  | UI exact total assertion (1 x Gel Pen should total 1.01) |
| BUG_04 | authorization_idor | critical | AC-06.2 | not run |  | Role / URL tampering (alice opens /orders/1) |
| BUG_05 | security_xss | critical | AC-03.5 | not run |  | Security probe (script/img payload in description) |
| BUG_06 | navigation | low | AC-08.1 | not run |  | Link check |
| BUG_07 | error_handling | high | AC-02.4 | not run |  | Edge-case input (search for %) |
| BUG_08 | accessibility | medium | AC-01.4 | not run |  | Accessibility scan (label / accessible name check) |
| BUG_09 | performance | medium | AC-02.6 | not run |  | Timing budget (2 s) |
| BUG_10 | state_machine | high | AC-05.4 | not run |  | Invalid state transition (checkout with empty cart) |
| BUG_11 | session | critical | AC-01.3 | not run |  | Reuse old session cookie / back button after logout |
| BUG_12 | concurrency | medium | AC-03.6 | not run |  | Double click / repeated submit |
| BUG_13 | wrong_message | medium | AC-01.2 | not run |  | Exact error text assertion |
| BUG_14 | sorting | low | AC-02.3 | not run |  | Order assertion on equal-price products |
| BUG_15 | pagination | medium | AC-02.5 | not run |  | Filter then paginate |
| BUG_16 | authorization_role | critical | AC-07.1 | not run |  | Role matrix (user opens /admin) |
| BUG_17 | upload_validation | high | AC-04.2 | not run |  | Disallowed file type upload |
| BUG_18 | required_validation | medium | AC-03.1 | yes | AC-03.1.2 exception flow: An empty or bl, AC-03.2.3 exception flow: A name of 51 o | Negative equivalence partition (empty name) |
| BUG_19 | search | low | AC-02.2 | not run |  | Equivalence partition on letter case |
| BUG_20 | persistence | high | AC-03.7 | not run |  | Reload check after delete |
| BUG_21 | validation_numeric | high | AC-05.1 | yes | AC-05.1.1 Quantity range min-1 (0) is re, AC-05.1.1 Quantity: negative number is r | Boundary-value analysis (quantity 0 / -1) |
| BUG_22 | business_rule | high | AC-05.3 | not run |  | Repeat action (apply SAVE10 twice) |

## Test design (Phase 3)

| Technique | Cases |
|---|---|
| bva | 21 |
| decision_table | 5 |
| ep | 15 |
| role_matrix | 14 |
| state_transition | 7 |
| use_case | 49 |

| Bug | Category | AC | Targeted | Techniques |
|---|---|---|---|---|
| BUG_01 | validation_boundary | AC-03.2 | yes | bva |
| BUG_02 | server_client_mismatch | AC-03.3 | yes | bva, ep |
| BUG_03 | calculation | AC-05.2 | yes | use_case |
| BUG_04 | authorization_idor | AC-06.2 | yes | use_case |
| BUG_05 | security_xss | AC-03.5 | yes | use_case |
| BUG_06 | navigation | AC-08.1 | no |  |
| BUG_07 | error_handling | AC-02.4 | no |  |
| BUG_08 | accessibility | AC-01.4 | no |  |
| BUG_09 | performance | AC-02.6 | no |  |
| BUG_10 | state_machine | AC-05.4 | yes | use_case |
| BUG_11 | session | AC-01.3 | yes | use_case |
| BUG_12 | concurrency | AC-03.6 | yes | use_case |
| BUG_13 | wrong_message | AC-01.2 | yes | ep, use_case |
| BUG_14 | sorting | AC-02.3 | no |  |
| BUG_15 | pagination | AC-02.5 | no |  |
| BUG_16 | authorization_role | AC-07.1 | no |  |
| BUG_17 | upload_validation | AC-04.2 | no |  |
| BUG_18 | required_validation | AC-03.1 | yes | bva, ep, use_case |
| BUG_19 | search | AC-02.2 | no |  |
| BUG_20 | persistence | AC-03.7 | yes | use_case |
| BUG_21 | validation_numeric | AC-05.1 | yes | bva, ep |
| BUG_22 | business_rule | AC-05.3 | yes | decision_table, use_case |

## Tests failing on the bug-free build

- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_create_a_product_with_valid_information.spec.ts::AC-01.2.1 Password: empty is rejected`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_create_a_product_with_valid_information.spec.ts::AC-01.2.1 Username: empty is rejected`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_create_a_product_with_valid_information.spec.ts::AC-03.1.1 exception flow: violate "Name is required."`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_create_a_product_with_valid_information.spec.ts::AC-03.2.1 exception flow: violate "Name must be 1–50 characters."`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_001_create_a_product_with_valid_information.spec.ts::AC-03.4.1 exception flow: violate "Category must be one of Books, Electronics or Home ("Please choose a category")."`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_002_validation_failure_for_blank_or_oversized_product_name.spec.ts::AC-03.1.1 Name length min-1 (0 chars) is rejected`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_002_validation_failure_for_blank_or_oversized_product_name.spec.ts::AC-03.1.1 Name: whitespace only is rejected`
- `bench_buggy_shop/test_creation/test_scripts/M03/test_M03_BS_006_duplicate_product_submission_prevention.spec.ts::AC-03.6.2 main flow: The Save button is disabled while saving.`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_001_add_product_to_cart_or_update_cart_quantity_with_valid_integer_quantity.spec.ts::AC-05.1.1 Quantity range max (99) is accepted`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_001_add_product_to_cart_or_update_cart_quantity_with_valid_integer_quantity.spec.ts::AC-05.1.1 Quantity range max-1 (98) is accepted`
- `bench_buggy_shop/test_creation/test_scripts/M04/test_M04_BS_001_add_product_to_cart_or_update_cart_quantity_with_valid_integer_quantity.spec.ts::AC-05.1.1 Quantity: non-numeric text is rejected`

## ACs with no linked executed test

AC-01.1, AC-01.3, AC-01.4, AC-02.1, AC-02.2, AC-02.3, AC-02.4, AC-02.5, AC-02.6, AC-03.5, AC-03.7, AC-04.1, AC-04.2, AC-05.2, AC-05.3, AC-05.4, AC-06.1, AC-06.2, AC-07.1, AC-08.1

> Heal probe disabled (--no-healing).

> --skip-generate: generation LLM usage/runtime are not part of this run.
