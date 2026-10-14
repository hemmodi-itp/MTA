# Phase 7 report — Non-Functional Test Types

Builds on Phase 7-mini (`64a8cbb`). Every type is its own `test_types` flag (absent = off), tuned under `nfr:`.

**Generator** (`tools/nonfunctional/generate.py`, deterministic, from app_map / form_model / baseline): one
`test_scripts/nfr/nfr_<type>.spec.ts` per enabled type; a type switched off has its spec removed. Runtime checks in
`fixtures/nfr.ts` (pure rules unit-tested; in-page probes).

| Type | What the generated tests check |
|---|---|
| accessibility | axe WCAG 2.0/2.1/**2.2** A+AA (critical/serious fail, moderate/minor warn), **accepted-issues baseline** (`nfr.accessibility.accepted`), **keyboard walk** (every focusable element reachable with Tab, no trap; missing focus ring warns), **form errors** (an empty submit of a non-destructive form with a required field is announced — role=alert / aria-live / native validation; focus on the field warns) |
| visual | full-page screenshot per state × viewport, dynamic regions masked; **the first run writes the baseline and passes**; `python -m tools.nonfunctional.visual approve --project X` re-runs with `--update-snapshots` |
| performance | TTFB / FCP / LCP / load / bytes / requests vs **budgets** and vs the Phase 2 **baseline timing** (regression > `regression_pct` → warn or fail); the 5 slowest requests annotated |
| security_passive | headers, cookie flags, tokens/PII in URL or localStorage, plus **stack-trace leaks, mixed content, target=_blank without noopener** — reads responses only |
| compatibility | viewports 320–1440 (+ landscape on phones): **no horizontal overflow** (fail), touch targets < 24 px and clipped text (warn) |
| resilience | **offline** then reconnect, **slow 3G** (Chromium CDP), **unusual characters** in GET (search) forms: no 5xx, no blank page, no stack trace, no uncaught page error |
| i18n | locale × timezone matrix (`test.use`), **RTL** flip, **+40% text expansion**: no overflow; clipping warns |

**Pipeline**: ScriptGenerationAgent runs the generator at the end of every run and registers the specs in
`test_suite.json` (`generation_mode: "nfr"`) and `test_plans.json` (one tc_id per test, ACs from title tags), so they
run with the suite and appear in **traceability** (buggy_shop: 186 NFR tests, 30 linked to ACs). States that need a
role use **`test.use({ role })`** when `execution.role_auth` is on. UIExecutionAgent gives `nfr/` specs the app's
origin as base URL (they navigate with absolute URLs). `@axe-core/playwright` **4.13.0** is now a pinned
devDependency.

**Fixes found while running it**: the browser's own failed-load page (`chrome-error://`) is no longer treated as
leaving `safety.allowed_hosts` (it failed every offline test); the generated renderer-appended console check ignores
the browser's "4xx resource" lines (Phase 5 fix, found here first); form-error checks never submit destructive forms.

**Benchmark** (`benchmarks/results/2026-10-14_buggy_shop_phase7_nfr.md`, `python -m tools.benchmark.nfr_bench`):
generated from bench_buggy_shop's real Phase 2 discovery, 104 tests, correct app vs each seeded non-functional bug —
a bug counts as detected only with a failing finding the correct app does not have.

| Seeded bug | Type | Detected | New finding |
|---|---|---|---|
| BUG_08 password field without label | accessibility | yes | axe `label` (critical) on /login |
| BUG_09 product list takes 3.5 s | performance | yes | ttfb / load over budget on /products |
| BUG_07 `%` in search → HTTP 500 | resilience | yes | server-error on the search form |

On the correct app all accessibility, visual, performance, responsive, resilience and i18n tests pass; the 11
security tests fail on **real** gaps of buggy_shop (no CSP, framing, Referrer-Policy, nosniff headers).

**Tests**: `tests/unit/test_nonfunctional_generate.py` 7 (every type, registration, role storage state, flag off,
passive spec never submits anything); vitest `fixtures/nfr.test.ts` 9 (rules); `safety.test.ts` +1;
`test_base_url_resolution.py` +1.

**Not done**: active security probes (XSS / SQL injection / open redirect / IDOR / auth bypass / CSRF / rate limit)
were not built in this pass — they need an explicit decision on scope and safeguards; the plan's "seeded XSS and IDOR
are detected" criterion is therefore not met by Phase 7 (stored XSS BUG_05 *is* caught by the Phase 5 oracles —
`verifyNoDialog` / `verifyNotInjected` — see the Phase 6 benchmark). Per-API fault injection and i18n format checks are
also open. See docs/backlog.md → Phase 7.
