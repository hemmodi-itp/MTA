# Buggy Shop benchmark app

A small local web shop (FastAPI + server-rendered HTML) with **22 seeded bugs**, all **off by
default**. It is the ground-truth target MTA runs against to measure bug detection
(see `docs/phases/phase-0-design.md` §3.1).

## Run

```bash
python -m benchmarks.apps.buggy_shop                # http://127.0.0.1:8765
python -m benchmarks.apps.buggy_shop --port 8799    # or set BENCH_PORT
```

It binds to `127.0.0.1` only. State is in memory and resets on every start.

Accounts: `alice` / `alice-pass-1` (role `user`), `admin` / `admin-pass-1` (role `admin`).
Seed data: 23 products in Books / Electronics / Home, order #1 owned by admin, order #2 owned by
alice, discount code `SAVE10` (10% off, once per cart).

## Toggling bugs

Flags are read from the environment **on every request**:

| Setting | Effect |
|---|---|
| (nothing) | correct app, no bugs |
| `BUG_07=1` | enable one bug |
| `BUGS=BUG_01,BUG_07` | enable a list |
| `BUGS=all` | enable all 22 |

```bash
BUGS=all python -m benchmarks.apps.buggy_shop          # bash
$env:BUG_04="1"; python -m benchmarks.apps.buggy_shop  # PowerShell
```

## Files

| File | Purpose |
|---|---|
| `app.py` | `create_app()` factory and module-level `app`; all bug branches live here |
| `bugs.py` | `is_on(bug_id)`, `enabled_bugs()` |
| `store.py` | deterministic in-memory seed (products, users, orders, carts, sessions) |
| `templates.py` | HTML (f-strings + `html.escape`) and the small client-validation script |
| `brd.md` | the BRD fed to MTA: `REQ-xx` requirements with `AC-xx.y` acceptance criteria |
| `bugs.yaml` | ground truth: `id, flag, title, category, severity, affected_ac, how_detectable` |
| `mta_project/project.yaml.tmpl` | MTA project manifest; substitute `{{BASE_URL}}` and `{{PROJECT_NAME}}` |

## Ground truth

`bugs.yaml` is the answer key. Each bug violates exactly one acceptance criterion in `brd.md`
(`affected_ac`). A detection counts when MTA reports a failure against that AC (or the matching
page/behaviour) while the bug is on, and does not when it is off.

| ID | Category | Affected AC |
|---|---|---|
| BUG_01 | validation_boundary | AC-03.2 |
| BUG_02 | server_client_mismatch | AC-03.3 |
| BUG_03 | calculation | AC-05.2 |
| BUG_04 | authorization_idor | AC-06.2 |
| BUG_05 | security_xss | AC-03.5 |
| BUG_06 | navigation | AC-08.1 |
| BUG_07 | error_handling | AC-02.4 |
| BUG_08 | accessibility | AC-01.4 |
| BUG_09 | performance | AC-02.6 |
| BUG_10 | state_machine | AC-05.4 |
| BUG_11 | session | AC-01.3 |
| BUG_12 | concurrency | AC-03.6 |
| BUG_13 | wrong_message | AC-01.2 |
| BUG_14 | sorting | AC-02.3 |
| BUG_15 | pagination | AC-02.5 |
| BUG_16 | authorization_role | AC-07.1 |
| BUG_17 | upload_validation | AC-04.2 |
| BUG_18 | required_validation | AC-03.1 |
| BUG_19 | search | AC-02.2 |
| BUG_20 | persistence | AC-03.7 |
| BUG_21 | validation_numeric | AC-05.1 |
| BUG_22 | business_rule | AC-05.3 |

## Stable element ids (for DOM scanners and setup steps)

- Login: `#login-form`, `#username`, `#password`, `#login-button`, error `#login-error` (`role=alert`)
- Nav: `#main-nav`, `#nav-products`, `#nav-new-product`, `#nav-cart`, `#nav-upload`, `#nav-admin`, `#logout-link`; footer `#footer-help-link`; flash `#flash` (`role=status`)
- Products: `#search-form`, `#search` (`q`), `#category-filter`, `#sort`, `#search-button`, `#product-list` > `[data-testid=product-item]`, `#result-count`, `#no-results`, `#prev-page`, `#next-page`, `#page-indicator`
- Product form: `#product-form`, `#name`, `#price`, `#category`, `#description`, `#save-product`, errors `#form-errors`
- Product detail: `#product-name`, `#product-price`, `#product-category`, `#product-description`, `#add-to-cart-form`, `#quantity`, `#add-to-cart`, `#edit-product`, `#delete-product`
- Cart: `#cart-table` > `[data-testid=cart-line]`, `#cart-subtotal`, `#cart-discount`, `#cart-total`, `#cart-empty`, `#cart-error`, `#discount-code`, `#apply-discount`, `#checkout-link`
- Checkout / orders: `#place-order`, `#checkout-error`, `#order-title`, `#order-confirmation`, `#order-total`
- Upload: `#upload-form`, `#file`, `#upload-button`, `#upload-result`, `#upload-error`
- Admin: `#user-table`; errors (403/404): `#error-message`

## Tests

```bash
python -m pytest tests/unit/test_bench_buggy_shop.py -q
```

Every bug has a test asserting correct behaviour with its flag off and buggy behaviour with it on.

## Locator changes (Phase 6 healing benchmark)

`LOC_01`..`LOC_12` (same switches as the bugs, e.g. `LOC_03=1`) change locators without changing behaviour — renamed
ids/test ids, a reworded button, wrappers, a moved link; `LOC_11`/`LOC_12` replace an element with a different one.
While any is on, target elements carry `data-bench-id` (ground truth). Defined in `locator_changes.py`; used by
`python -m tools.benchmark.healing_bench`.
