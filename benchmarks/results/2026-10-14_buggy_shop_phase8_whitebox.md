# Phase 8 white-box benchmark — buggy_shop (2026-10-14)

White-box rules from `benchmarks/apps/buggy_shop` source: 26 routes, 10 rules (each cites file:line). App run under coverage.py (branch).

| KPI | Result | Target |
|---|---|---|
| API endpoint coverage | **96.2%** of 26 | ≥ 90% |
| Code coverage collected | statements 61.8%, branches 29.1% (UI baseline) | yes |
| One gap round raises branch coverage | **29.1% → 63.8%** (statements 61.8% → 82.9%) | measurable rise |
| "Server accepts what the client rejects" bugs caught by an API test | **1/1** | all |
| Other seeded bugs caught by the API suite | 7/9 | — |

Frontend (V8): 0/0 JS functions ran in the baseline (None%; inline scripts, no source maps).

Gap round: 40 function(s) with uncovered lines → API tests for 25 route(s): POST /api/products, POST /upload, POST /products/{id}/edit, POST /checkout, POST /cart/discount, POST /cart/update, POST /products, GET /api/orders/{id}, POST /products/{id}/delete, GET /orders/{id}, GET /api/products, GET /products/{id}/edit.

## Seeded bugs vs the API suite

| Bug | Detected | First failing API test(s) |
|---|---|---|
| BUG_02 (server/client mismatch) | yes | POST /api/products — price below min (-0.01) -> rejected [benchmarks/apps/buggy_shop/app.py:99] @api @api-rule<br>POST /products — price below min (-0.01) -> rejected [benchmarks/apps/buggy_shop/app.py:99] @api @api-rule |
| BUG_01 | yes | POST /api/products — name at max length 50 -> accepted [benchmarks/apps/buggy_shop/app.py:85] @api @api-rule<br>POST /products — name at max length 50 -> accepted [benchmarks/apps/buggy_shop/app.py:85] @api @api-rule |
| BUG_18 | yes | POST /api/products — name empty -> rejected [benchmarks/apps/buggy_shop/app.py:82] @api @api-rule<br>POST /api/products — name missing -> rejected [benchmarks/apps/buggy_shop/app.py:82] @api @api-rule |
| BUG_21 | yes | POST /cart/add — quantity below min (0) -> rejected [benchmarks/apps/buggy_shop/app.py:163] @api @api-rule |
| BUG_17 | no | — |
| BUG_16 | yes | GET /admin — as user (needs admin) -> 403 @api @api-role |
| BUG_04 | yes | GET /api/orders/{id} — /api/orders/1 as user (owned by admin) -> denied @api @api-ownership<br>GET /orders/{id} — /orders/1 as user (owned by admin) -> denied @api @api-ownership |
| BUG_07 | yes | GET /api/products — unusual query values never 5xx @api @api-query<br>GET /products — unusual query values never 5xx @api @api-query |
| BUG_13 | no | — |

## Mutation score (validate_product, parse_quantity)

10/12 mutants killed — **83.3%**. Survivors:
- line 85 validate_product: GtE -> Gt
- line 161 parse_quantity: Gt -> GtE

## Uncovered critical functions after the UI baseline

- api_create_product (benchmarks/apps/buggy_shop/app.py): 14 line(s)
- upload (benchmarks/apps/buggy_shop/app.py): 14 line(s)
- edit_product (benchmarks/apps/buggy_shop/app.py): 13 line(s)
- place_order (benchmarks/apps/buggy_shop/app.py): 12 line(s)
- cart_discount (benchmarks/apps/buggy_shop/app.py): 11 line(s)
- cart_update (benchmarks/apps/buggy_shop/app.py): 11 line(s)
- validate_product (benchmarks/apps/buggy_shop/app.py): 10 line(s)
- api_order (benchmarks/apps/buggy_shop/app.py): 9 line(s)
- delete_product (benchmarks/apps/buggy_shop/app.py): 9 line(s)
- order_page (benchmarks/apps/buggy_shop/app.py): 9 line(s)

## Contract findings (frontend vs backend)

- server_weaker: POST /login (form login-form on /login) username — the browser enforces required on 'username' but the server does not — a request that skips the UI is accepted
- server_weaker: POST /login (form login-form on /login) password — the browser enforces required on 'password' but the server does not — a request that skips the UI is accepted
