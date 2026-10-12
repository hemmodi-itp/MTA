# Phase 4 — Playwright Runtime Modernization: Design Note (session 2 of 2)

> Checked against the code on 2026-10-12 at `e96b03d` (Phase 4 session 1), branch `mta-v3/phase-4`.
> **Scope:** 4.4 fixtures (+ `fullyParallel` gating), 4.5 `test.step` + `test.use({ role })` rendering,
> 4.6 waiting, 4.7 flaky / skipped / browser-close classification, with their tests. Acceptance criteria 1, 2, 3, 7
> and 8 are proved in this session; 4–6 are re-run (`tests/integration/test_phase4_runtime_e2e.py`).
> Where this note and the plan disagree, §9 lists the change and why. Session 1's report still holds where this
> note doesn't touch a topic. Decisions I need from you are in §11.

---

## 1. Verified facts (assumption → what the code does)

| # | Assumption | Reality (file:line at `e96b03d`) | Consequence |
|---|---|---|---|
| G1 | `retries: 0`, no `fullyParallel` | **Confirmed.** `buildConfig.ts:183` `retries: 0`, no `fullyParallel` key; `workers: CI ? 1 : 2`. UIExecution always passes `--workers=2` headless / `1` headed (`agent.py:542`). Without `fullyParallel`, **files** already run in parallel on 2 workers. Only tests **inside one file** are sequential. | `fullyParallel` only adds parallelism within a file. |
| G2 | UIExecution counts flaky as a pass, skipped as failed | **Confirmed.** `_parse_playwright_json` (`agent.py:1242`) `ok = status in (passed, expected, flaky)` → `status: "success"`; anything else, Playwright `skipped` included, becomes `"failed"`. `_count_results` (`:115`) counts `success`/`expected` as passed. | 4.7 changes the parser *and* the source. |
| G3 | The MTA reporter has the right statuses | **Confirmed.** `mta-reporter.ts:22` `testStatus()` (flaky from `outcome()`). `tools/execution/mta_results.py::to_execution_results` keeps `status: "flaky"` but **drops** `test_case_id` / `business_scenario_id`, which `stamp_execution_results` (test_suite.json) and `report_writer` need. It is **not called** by UIExecution yet. | Add those two fields and switch the source (E10). |
| G4 | Every flaky consumer | Flaky becomes a pass in **5 places:** UIExecution parser (`agent.py:1242`), traceability `result_status` (`traceability.py:244`; `LatestResult.status` Literal has no `flaky`, `tools/requirements/models.py:229`; `TraceAC.result` neither, `:269`), benchmark `score.py:41` (`"flaky": PASS`), test_suite.json stamp (`catalog_manager.py:143`, writes the raw status, so `success` → `passed`), HTML report pill (`html_report.py:234`: anything not `success` → "✗ FAILED"). Healing **already excludes** flaky (`healing/tools.py:189`); `_run_tests` (`:778`) only clears a test on `success`. | All five change (E10–E12). Healing keeps excluding flaky; a test that is flaky after a patch is not counted as healed. |
| G5 | Browser-close → skipped is unconditional | **Confirmed.** `_mark_browser_close_as_skipped` runs on every parse (`agent.py:693`) and in `_recover_partial_results` (`:1409`), headed or not. `"target crashed"` and `"connection closed"` are in the pattern list (`:76-86`), so a headless crash is reported as skipped. | Gate on headed (E13). |
| G6 | Module logins render as `beforeEach` with literals + `waitForTimeout(500)` | **Confirmed.** `_translate_setup_step` (`script_generation/agent.py:1412-1447`) renders `wait: N` → `page.waitForTimeout(N)` and literal `value:` fills. `_inject_setup_steps` (`:1450`) adds the hook after `test.describe(`. All 6 benchmark specs have it (literal `alice-pass-1`). Playwright records those `fill()` values in the trace and HTML report today. | `module_roles` (E8) removes the literals; `wait:` gets a web-first translation (E9). |
| G7 | `click()` waits for the navigation it starts | **Verified in 1.64.0:** `waitForSignalsCreatedBy` (`playwright-core/lib/coreBundle.js`) holds a `SignalBarrier` until navigations requested by the action **commit** (unless `noWaitAfter`). A POST → 303 → GET commits on the final GET. | After the setup `click`, `waitForLoadState('load')` reliably waits for the landing page — no sleep needed (E9). |
| G8 | waitForTimeout in the LLM vocabulary | `ALLOWED_ACTIONS` (`script_generation/agent.py:85-93`) contains it; the prompt lists it (`prompt.py:94`) and the LLM also gets `sorted(ALLOWED_ACTIONS)` (`agent.py:659`). The renderer (`spec_renderer.py:145,187,223,239`) and flows rendering share `ARG_BUILDERS`. Existing usage: `waitForTimeout` in 93 spec files across 6 projects (mostly the setup `beforeEach`); one LLM plan (`geminitest4/test_plans.json`); no `flows.json` uses it. The 61 benchmark tests use none in their plans. | Remove from `ALLOWED_ACTIONS` + prompt; keep it in the renderer (flows) and ActionEngine (E9). |
| G9 | `propose_timing_fix` may suggest sleeps | It returns only `{is_timing_issue, locator, resolved_within_ms}` (`healing/tools.py:550-580`). The LLM writes the new block, and nothing stops `waitForTimeout` in it; `apply_patch` (`:697`) checks structure and the details object only. `_extract_locator_calls` finds raw `page.getBy…` calls, so action-library specs get "no locator call found". | Add a web-first suggestion + an `apply_patch` guard (E14). |
| G10 | Healing block extraction works on nested blocks | `_extract_test_block` (`:220`) anchors on `test(` / `test.skip(` / `test.fixme(` + title and brace-counts with string awareness. `test.step(` does not match the anchor (`test` must be followed by `(`, `.skip` or `.fixme`). `_header_details` reads the first `test(` line. `_structurally_valid_block` counts `{}`/`()` **including inside strings**. | Step wrapping is compatible. Step titles must not add unbalanced brackets (E7). |
| G11 | `baseline.json` for consoleGuard | `test_comprehension/baseline.json` (contract `baseline` v2): `states{ id: {url, role, console_errors[{text, source}], console_warnings, page_errors, failed_requests, timing{ttfb_ms, dcl_ms, load_ms, fcp_ms, transfer_bytes, requests}} }`. benchmark: 23 states, one real baseline error: role `user` on `/admin` → `Failed to load resource: … 403 (Forbidden)`. | Match new errors by (URL path, normalised text) (E3). Phase 7 perf budgets can use `timing`. |
| G12 | Console errors in buggy_shop negative tests | buggy_shop answers invalid forms with **HTTP 400** (`app.py` `_form_page(..., 400)`) and bad logins with 401. Chromium logs `Failed to load resource: … 400` as a **console error** for the document. Many Phase 3 negative tests hit that. | `consoleGuard` **cannot default to `fail`** without failing correct negative tests. Default `warn` (E3). |
| G13 | Data collisions are real on buggy_shop | `create_or_dedupe` (`app.py:110`) returns the **existing** product when name + price match one created in the last 5 s (`DEDUP_WINDOW_S`). Sessions live in memory (`store.py:92`; lost on restart), the flash message is **per session**, and carts are **per username** (`store.py:cart`). No REST delete: `POST /products/{id}/delete` (form, session cookie). `/api/products` GET/POST exist. | Same literal data in two workers → the second create silently lands on the first worker's product. This is the collision criterion 2 must rule out (E1, §8). |
| G14 | A shared role session is safe | **Not on buggy_shop:** with `test.use({ role: 'user' })` every test of a run shares one `sid` cookie, so parallel tests can consume each other's flash message. Today each test logs in (own session). And `.auth/<role>.json` is reused for 30 min (`role_auth_max_age_minutes`), but the benchmark restarts the app per bug → stale session (session-1 open issue 1). | `module_roles` stays off by default and in the benchmark template (§11 Q2). |
| G15 | `failOnFlakyTests` exists | `node_modules/playwright/types/test.d.ts:1324` (config) — session 1 also found the CLI flag. | `failOnFlakyTests: CI` (E11). |
| G16 | HAR via Playwright | `recordHar` exists only as a **context option** (`contextOptions`), is written when the context closes (after test-scoped fixtures tear down), and records cookies, `Authorization` headers and POST bodies — including the login form's password. | Build the HAR from request/response events, redacted (E5). |
| G17 | Destructive rules are Python-only | `tools/safety/action_classifier.py` (`classify_step`) + `destructive_rules.yaml` (phrases, `safe` overrides, URL patterns). Policy: `SafetyPolicy.destructive_allowed = allow_destructive and environment ∈ {local, dev, staging}` (`policy.py:97`). UIExecution passes the host list as `MTA_ALLOWED_HOSTS` but nothing about destructive actions. The runtime has the locator entries via `LocatorManager.get(key)`. | TS port reads the **same YAML**; a shared case file keeps both classifiers equal (E6). |
| G18 | Benchmark ids survive the source switch | `run.py:142` test id = `spec_file::test_title`. The MTA reporter's `spec_file` is relative to `project.testDir`; the Playwright JSON's `spec.file` is relative to `rootDir` = the same `PW_TEST_DIR`. Titles are unchanged by `test.step`. | Before/after comparison stays per test. Verified again in the integration test. |
| G19 | The benchmark project can be re-rendered | `test_plans.json` stores each **traced** plan (`tc_id`, `ac_ids`, tags) after `PlanTracer.annotate` (`agent.py:396-397`); all 6 benchmark specs are `generation_mode: action_library`. `tools/benchmark/run.py` re-materialises `project.yaml` from `benchmarks/apps/buggy_shop/mta_project/project.yaml.tmpl` on **every** run, `--skip-generate` included. | A deterministic re-render CLI is enough (E15). Benchmark flags go into the template. |
| G20 | Run id for testData | UIExecution sets `MTA_RUN_ID` (`agent.py:573`); a hand run doesn't. Playwright workers inherit the runner's environment, and the config is evaluated in the runner first. | `playwright.config.ts` sets `MTA_RUN_ID` when it is missing, so all workers of a hand run share one id (E1). |
| G21 | No new npm dependency needed | Deterministic data: a 30-line seeded PRNG is enough. axe: Phase 7 does the checks. | No `faker`, no `@axe-core/playwright` now (E1, E4). |
| G22 | Report consumers of the result list | `report_writer.py:216-230` copies `status` + `flaky` per test and computes `pass_rate = passed / scenarios_executed`. The 4-level CLI (`suite_orchestrator.py:226,319`) only looks at the return code. `agents/evaluation/*` use their own pipeline, not UIExecution results. | Additive: `flaky` / `skipped` counts and a FLAKY / SKIPPED pill. |

## 2. Decisions

### 4.4 Fixtures (`application_assets/_shared/runtime/fixtures/testFixture.ts`, extended, `action` + `role` unchanged in use)

New code goes in small modules next to the fixture (`runtime/fixtures/*.ts`, each with a vitest file). `testFixture.ts`
only wires them into `base.extend`. Fixture options come from the resolved `execution:` block (§3), read once per worker
through `loadProjectYaml(PW_PROJECT)`.

| # | Fixture | Decision |
|---|---|---|
| **E1** | `testData` | **Seed** = FNV-1a of `MTA_RUN_ID | testInfo.testId | repeatEachIndex | retry` → `mulberry32` PRNG. Same inputs → same data (determinism), a retry or a `--repeat-each` copy gets fresh data (so an entity a failed attempt left behind can't collide with the retry). **Prefix** `mta<run6><test4>` (e.g. `mta7f3a2c9e1b`: 6 base-36 chars of the run hash + 4 of the test hash, ≤ 13 chars, so it fits buggy_shop's 50-character name limit). API: `runId`, `prefix`, `unique(label, {maxLength?})` → `"<prefix>-<label>-<n>"` (counter per test), `email(label)` → `<prefix>.<label>@example.test` (RFC 2606 reserved), `int(min, max)`, `string(len, alphabet?)`, `pick(list)`. **No faker:** we need uniqueness + determinism, not realistic names; faker adds a large dependency whose output can change between versions. `MTA_RUN_ID` missing (hand run) → `playwright.config.ts` sets `local-<timestamp>` before workers start (G20). |
| **E2** | `cleanup` + `api` | **`api`**: `playwright.request.newContext({ baseURL, storageState, extraHTTPHeaders? })`, where `storageState` is the role's (`resolveRoleStorageState`, the same function the `role` option uses) or the config's `PW_STORAGE_STATE`, and `baseURL` is the run's. Disposed at teardown. Absolute URLs outside `MTA_ALLOWED_HOSTS` are refused (same `isUrlAllowed`). **`cleanup`**: `cleanup.register(label, { api?: (api) => …, ui?: (page) => … })`. Teardown runs the entries in **reverse** order; each tries `api` first and falls back to `ui` when `api` is missing or throws. A failure is **never swallowed**: annotation `{ type: 'cleanup_failed', description: '<label>: <error>' }`, a `cleanup.json` attachment, a `console.warn`, and a new MTA reporter field `cleanup_failures[]` (E16). It does not change the test's status unless `execution.cleanup_failure: fail` (then teardown throws, so the test fails). |
| **E3** | `consoleGuard` | **Auto fixture** on the **context** (`context.on('console')` for `error`, `context.on('weberror')` for page errors), so it also covers popups and doesn't create a page for API-only tests. At teardown each error is compared with `baseline.json`: **known** = the same normalised text (whitespace collapsed, ANSI removed) recorded for a state whose URL path equals the page's path (origin and query ignored). Anything else is **new**. Mode `execution.console_guard`: `off` (no listeners) / `warn` (annotation `console_new_error` per error + `console-errors.json` attachment; test status unchanged) / `fail` (also throws at teardown, listing the new errors). **Default `warn`** (G12). Missing or unreadable baseline → warn-only, with annotation `console_guard: no baseline.json at <path> — new-error check is warn-only`. Exposes `consoleGuard.errors()`, `newErrors()`, `knownErrors()` for Phase 5's `verifyNoNewConsoleErrors`. The existing `action.verifyNoPageErrors` is unchanged. |
| **E4** | `a11y` | **Stub with wiring, no dependency.** `a11y.scan(options)` loads `@axe-core/playwright` lazily (`require` in a try block). Not installed → a clear error: "a11y checks arrive with Phase 7 — `npm i -D @axe-core/playwright` to use AxeBuilder now". Installed → `new AxeBuilder({ page }).withTags(options.tags).analyze()`, results attached as JSON. No assertions (Phase 7). |
| **E5** | `network` | **Auto fixture** on the context unless `execution.network: off`. Records `{method, url, resource_type, status, status_text, request_headers, response_headers, post_data (≤ 4 KB), started_at, duration_ms, failure}` per request. API for Phase 5: `requests(filter?)`, `responses(filter?)`, `last(urlPattern)`. HAR 1.2 built **by us** from those events (G16), **redacted**: `cookie`, `set-cookie`, `authorization`, `proxy-authorization`, `x-api-key`, `x-auth-token`, `x-csrf-token` values → `[REDACTED]`; form / JSON / query fields whose name matches `/pass|secret|token|otp|pin|cvv|card|ssn/i` → `[REDACTED]`. No bodies of responses. Attached as `network.har` when the test failed (`network: on-failure`, default) or always (`on`). |
| **E6** | `safety` | **Auto fixture** holding `RuntimeSafety` = `{ allowedHosts, violations, destructive: { allowed, reason } }`. (a) Host guard: the `framenavigated` listener moves from `action` into this fixture (every page of the context), so raw-`page` specs (setup `beforeEach`) are guarded too. ActionEngine still throws on the next action, as today. **New:** a violation that no action reported fails the test at teardown. (b) **Destructive guard:** a TS port of `classify_step` (`runtime/safety/actionClassifier.ts`) that reads `tools/safety/destructive_rules.yaml` with the `yaml` package (one rule file for both sides). ActionEngine classifies every interaction action (`click`, `doubleClick`, `pressKey` Enter, `check`/`uncheck`, `select…`, `dragAndDrop`) by locator key + `LocatorManager.get(key)` entry, and `navigate` by URL pattern, exactly like `classify_step`. Destructive and not allowed → `SafetyError("destructive action refused: click 'delete_account' (delete: phrase 'delete') — safety.allow_destructive=false / environment=prod")`. **Policy source:** `MTA_DESTRUCTIVE_ALLOWED=0/1` (+ `MTA_SAFETY_ENVIRONMENT`), set by UIExecution from `SafetyPolicy.destructive_allowed`. When unset (hand run), derive the same rule from PW_PROJECT's `environment:` + `safety.allow_destructive`. With no project at all: not enforced, one warning (like `MTA_ALLOWED_HOSTS`). Plans are already filtered at generation (`filter_plan`); this catches human-authored flows, healed specs and drift. |
| **E6b** | `perf` | **Wiring only.** `perf.collect()` → `page.evaluate` of Navigation Timing L2 (`ttfb_ms`, `dcl_ms`, `load_ms`, `transfer_bytes`, request count) + paint (`fcp_ms`) + buffered `PerformanceObserver` for `largest-contentful-paint` and `layout-shift` (`lcp_ms`, `cls`); the same field names as `baseline.json` `timing`, plus `lcp_ms` / `cls`. `perf.attach(name)` adds the JSON to the report. No budgets (Phase 7). Not auto. |
| **E6c** | `fullyParallel` | New `execution.data_isolation` (default `false`). `true` → `fullyParallel: true` in the config builder (the slot noted at `buildConfig.ts:181`). It is the project author's statement that its specs create data through `testData`; the runtime can't verify that. UIExecution keeps `--workers=2`. |

### 4.5 Structure (`spec_renderer.py`)

| # | Decision |
|---|---|
| **E7** | **`test.step` per plan step**, behind `execution.test_steps` (**default `true`** for newly generated specs; `render_spec_from_plan(..., test_steps=False)` stays the function default, so legacy callers and the existing golden tests are byte-identical). Rendered shape:<br>`    await test.step("3. Click \"save_product_button\"", async () => {`<br>`      await action.click("save_product_button");`<br>`    });`<br>The test line (title, `{ tag, annotation }` details object on **one** line, `({ action })`) is unchanged, so traceability, `--grep` and healing's details guard are unaffected. **Step title** = `"<n>. <phrase>"` from the plan step, deterministic, e.g. `Navigate to "/products/new"`, `Enter "Validxxx" into "name"`, `Select "Books" in "category"`, `Press "Enter" in "search"`, `Verify "product_form_errors" contains "Price is required"`, plus ` — <message>` when the step has one. `useFlow` → `Flow login(username="alice", password=•••)`. **Secrets:** a value whose locator key, flow parameter or locator entry says password/secret/token/pin/otp is shown as `•••` (step titles land in the HTML report and the trace). Titles longer than 160 characters are cut at a word boundary; if a cut (or a value) would leave unbalanced `()` / `{}`, the value preview is dropped (G10). Flows (`flows.generated.ts`) are not wrapped inside; the `useFlow` call is one step. The MTA reporter records the **failed step title** per attempt (`attempts[].failed_step`), so reports and Phase 6 triage can name the plan step that failed. |
| **E8** | **`test.use({ role })` for modules** — session-1 open issue 2. New optional `modules[].role` (an `auth.roles` name). When `execution.module_roles: true` **and** the module has a declared `role`, the renderer emits `test.use({ role: "<role>" });` (after the `baseURL` line) and **no** setup `beforeEach`. Otherwise today's `beforeEach` (with E9's waiting). Generation warns when `module_roles` is on but `role_auth` is off (the `.auth` files won't be written) or the role isn't declared (falls back to setup steps). The module's `setup:` stays the discovery recipe for the scanner. **Default `false`** (G14). |

### 4.6 Waiting

| # | Decision |
|---|---|
| **E9** | (a) `waitForTimeout` leaves `ALLOWED_ACTIONS` (so also the `valid_actions` list the LLM sees) and the prompt example (`prompt.py:94`). `_validate_plan` rejects it with a specific message ("`waitForTimeout` is not allowed in generated plans — use `waitForElement` or a `verify*` step; they wait automatically"), which goes through the normal retry / fallback path. (b) The renderer keeps the arg builder, for human-authored `flows.json`; ScriptGeneration logs a warning per flow that uses it. (c) ActionEngine keeps `waitForTimeout`, now with `Logger.warn` + a test annotation `{ type: 'warning', description: 'fixed sleep waitForTimeout(<ms>) — prefer a web-first wait' }`. (d) **Module setup `wait: N`** renders `await page.waitForLoadState('load');` (G7: the preceding `click` has already waited for its navigation to commit). No fixed sleep, and no `networkidle` wait that could hang on streaming apps. The scanner's own `wait:` (discovery, Python) is unchanged. (e) **ActionEngine helpers** (runtime API, not LLM vocabulary): `waitUntil(description, fn, {timeout, intervals})` → `expect(fn, description).toPass(...)`; `pollUntil(description, fn, expected, {timeout, intervals})` → `expect.poll(fn, ...).toEqual(expected)`; `waitForUrl(urlOrRegex)` → `page.waitForURL`; `waitForLoadState(state)`. All go through `run()`, so failures keep the `[locator_key=…]` tagging. Every existing `verify*` already uses web-first `expect(locator)` assertions. `navigate` keeps its bounded best-effort `networkidle` (≤ 5 s, never a fixed sleep). |
| **E14** | **Healing.** `propose_timing_fix` adds `suggested_fix` = a web-first replacement for the located call (`await expect(page.getByRole(...)).toBeVisible();` for raw specs), and `forbidden: "page.waitForTimeout / action.waitForTimeout"`. `apply_patch` rejects a new block that contains **more** fixed sleeps (`waitForTimeout(` / `setTimeout(`) than the old one, with a reason that names the web-first alternatives. One prompt line is added ("never add fixed sleeps"). This strengthens the tool boundary; the tool set is unchanged. |

### 4.7 Flakiness

| # | Decision |
|---|---|
| **E10** | **Retries.** `execution.retries: auto` (default) → **2 in CI** (`CI` set), **1 locally**, an integer 0–5 overrides. **Headed runs always pass `--retries=0`** (UIExecution and the 4-level CLI): a human closing the window must not relaunch the test. Resolved in Python and TS (shared case file). |
| **E11** | **`failOnFlakyTests`**: `execution.fail_on_flaky_tests: auto` (default) → true when `CI` is set; boolean overrides. It changes the exit code only; UIExecution's per-test results are the same. |
| **E12** | **Source of truth = the MTA reporter file.** `_run_playwright` / `_merge_only` / `_rerun_headless` read `mta/{ts}.mta_results.json` through `mta_results.to_execution_results` (extended with `test_case_id`, `business_scenario_id`, `pw_status`, `project`). The Playwright JSON stays the fallback when the MTA file is missing (`mta_reporter: false`, interrupted run, reporter crash), with the same status mapping. **Result `status` values:** `success` (passed), `flaky`, `failed` (failed / timedOut / interrupted, `pw_status` keeps which), `skipped` (**Phase 1 D6 fixed:** Playwright skipped stays skipped). Counts: `passed` (= `success` only), `flaky` (**new**), `failed`, `skipped`; `scenarios_executed` = the sum. A flaky test is **never** counted as passed. The same statuses flow into `execution_results` (+ `flaky` count), `_merge_runs`, the report index, `traceability.json` (`LatestResult.status` and `TraceAC.result` gain `flaky`; AC aggregation: any `failed` → failed/mixed as today, else any `flaky` → `flaky`; new summary key `acs_flaky`), `test_suite.json` (`last_result: "flaky"` / `"skipped"`), the ReportingAgent JSON/HTML (`flaky` + `skipped` counts, "⚠ FLAKY" and "○ SKIPPED" pills; pass rate = passed / executed, so flaky lowers it) and the benchmark scorer (E12b). |
| **E12b** | **Benchmark scorer:** `normalize_status("flaky")` → new `FLAKY`. A flaky test counts as executed, is **not** a stable pass (so it can't "catch" a bug), is **not** a catch in a bug run, is **not** a false failure, and counts as flaky when it is `flaky` in any clean run **or** its outcome differs across clean runs. Old result files rescore unchanged (they never stored `flaky`). |
| **E13** | **Browser-close.** `_mark_browser_close_as_skipped(results, headed=…)` reclassifies only when the run was **headed** (a human can close the window), and then only the human-close patterns (`target closed`, `page/browser has been closed`, `browser was disconnected`). `target crashed` / `connection closed` stay errors in both modes. Headless/CI: the test stays `failed`, with `error_kind: "browser_closed"` and a comment "browser closed unexpectedly in a headless run — counted as an error". The 3-closes → re-run headless logic (`_find_headless_threshold`) only runs headed, as today. `_recover_partial_results` gets the same flag. |
| **E16** | **MTA reporter** (additive, contract `mta_results` v2 stays v2: optional fields): `attempts[].failed_step` (title of the innermost failed `test.step`, E7) and `cleanup_failures[]` (from `cleanup_failed` annotations, E2). `MtaResultsV2` model + `schemas/mta_results.v2.schema.json` regenerated (that file only). |

### Re-rendering (migration)

| # | Decision |
|---|---|
| **E15** | New `tools/test_creation/script_generator/rerender.py` (+ `python -m tools.test_creation.script_generator.rerender --project X [--check] [--spec ID]`). For every `test_suite.json` spec with `generation_mode: action_library` **and** a plan in `test_plans.json`, it rebuilds the spec through **the same function ScriptGeneration uses**. I extract `compose_spec(plan, scenario, effective_url, spec_rel_path, project, flows_meta, module_setup, module_role, options)` from `ScriptGenerationAgent.execute` (render + role / setup injection), so the CLI and the agent can't drift. No LLM, no validation of the stored plan against the new vocabulary (a stored plan with `waitForTimeout` still renders, with a warning). `--check` prints a unified diff and writes nothing. Writes atomically and keeps a `.bak` copy (the benchmark copy already ignores `*.bak`). **Fidelity proof:** before any renderer change, `--check` with the legacy options must report **zero diff** on the 6 benchmark specs. |

## 3. project.yaml flags and defaults (`execution:`, both resolvers + `tests/fixtures/execution_config_cases.json`)

```yaml
execution:
  # … session-1 keys unchanged …
  retries: auto                 # auto = 2 in CI, 1 locally; 0-5 overrides. Headed runs always run with 0.
  fail_on_flaky_tests: auto     # auto = true in CI (exit code only)
  data_isolation: false         # true -> fullyParallel: true (specs create data through testData)
  console_guard: warn           # off | warn | fail — new console/page errors vs test_comprehension/baseline.json
  network: on-failure           # off | on-failure | on — request log; redacted HAR attached on failure / always
  cleanup_failure: warn         # warn | fail — a cleanup error is always reported; fail also fails the test
  test_steps: true              # renderer: one test.step per plan step (new / re-rendered specs)
  module_roles: false           # renderer: modules[].role -> test.use({ role }) instead of the setup beforeEach
modules:
  - id: M03
    role: user                  # new, optional: an auth.roles name (used only with module_roles: true)
```

Invalid values → default + one warning (the session-1 rule). `retries` / `fail_on_flaky_tests` resolve to the raw
value (`"auto"` or the override); `auto` is evaluated where `CI` and headed are known (config builder, UIExecution),
with one helper per side (`effectiveRetries`, `effective_retries`) and its own cases.

**What changes for a project with no new keys:** (a) **retries 1 locally / 2 in CI** — a fail-then-pass becomes `flaky`
and a failing test runs one more time; (b) `flaky` and `skipped` statuses appear in results and reports; (c) headless
browser-close errors are failures; (d) `consoleGuard` / `network` annotate and attach, they never fail a test;
(e) a navigation outside `allowed_hosts` that no action noticed now fails the test at teardown; (f) a destructive
action at run time is refused unless the policy allows it (the same policy that already filters plans). Existing spec
files are not touched until re-rendered.

## 4. Files

**New (TS, each with a `*.test.ts`)** — under `application_assets/_shared/runtime/`:
`fixtures/testData.ts`, `fixtures/cleanup.ts`, `fixtures/api.ts`, `fixtures/consoleGuard.ts`, `fixtures/network.ts` (+ HAR
builder / redaction), `fixtures/a11y.ts`, `fixtures/perf.ts`, `fixtures/options.ts` (execution options for fixtures),
`safety/actionClassifier.ts`, `safety/policy.ts` (destructive policy from env / project.yaml).

**New (Python / tests / fixtures)**
- `tools/test_creation/script_generator/rerender.py` (CLI, E15).
- `tests/fixtures/destructive_cases.json` (shared pytest + vitest classifier cases), `tests/fixtures/step_title_cases.json` if useful.
- pytest: `test_spec_renderer_steps.py` (golden snapshots: steps, tags, annotations, role rendering, secrets, brackets), `test_plan_validator_wait.py`, `test_rerender_specs.py`, `test_ui_execution_flaky_classification.py` (MTA source, JSON fallback, flaky / skip / browser-close headed vs headless, counts, retries flag), `test_traceability_flaky.py`, `test_catalog_flaky.py`, `test_benchmark_scorer_flaky.py`, `test_healing_step_wrapped.py` (block extraction, details guard, sleep guard, timing suggestion), `test_execution_config_phase4b.py` (new keys; shared cases), `test_safety_classifier_shared_cases.py`.
- Integration: `tests/integration/test_phase4b_runtime_e2e.py` + specs in `tests/e2e/phase4b/` (project `bench_p4b_e2e`, real Chromium + buggy_shop): criteria 2, 3, 7.

**Changed**
- `runtime/fixtures/testFixture.ts` (wire the fixtures; `framenavigated` moves to `safety`; `action` and `role` keep their API), `runtime/ActionEngine.ts` (helpers, `waitForTimeout` warning, destructive guard), `runtime/config/{execution,buildConfig}.ts` (new keys, `retries`, `fullyParallel`, `failOnFlakyTests`), `runtime/reporters/mta-reporter.ts` (E16), `playwright.config.ts` (`MTA_RUN_ID` default).
- `tools/execution/config.py`, `tools/execution/mta_results.py`, `tests/fixtures/execution_config_cases.json`.
- `tools/test_creation/script_generator/spec_renderer.py` (E7, E8 helpers).
- `agents/test_creation/script_generation/{agent.py, prompt.py}` (`ALLOWED_ACTIONS`, validator, `compose_spec`, setup translation, role rendering, flow warning), `agent.md` / `agent.json`.
- `agents/test_execution/ui_execution/agent.py` (E10, E12, E13, safety env vars), `agent.md` / `agent.json` (1.4.0).
- `agents/test_execution/healing/{tools.py, prompt.py}` (E14, flaky-after-patch), `agent.md` / `agent.json`.
- `agents/test_execution/reporting/` callers via `tools/test_execution/reports/{report_writer,html_report}.py` (counts, pills).
- `tools/requirements/{models,traceability}.py` (flaky), `tools/catalog/catalog_manager.py` (stamp), `tools/benchmark/{score,report_md}.py`, `tools/suite_orchestrator.py` (`--retries=0` headed).
- `contracts/artifacts/models.py` (`MtaResultsV2` optional fields) → `schemas/mta_results.v2.schema.json`; `tools/requirements/models.py` → `schemas/traceability.v2.schema.json` (enum gains `flaky`).
- Templates: `aAprojectTemplate/project.yaml` (commented new keys), `benchmarks/apps/buggy_shop/mta_project/project.yaml.tmpl` (`modules[].role`, `module_roles: false`, see §8).
- Docs: README (Execution, Playwright configuration, Script Generation, Self-Healing, Suite Manifest note on `last_result`), `docs/audit/current_state.md` if a fact there changes.

**Not touched:** `frontend/**`, `api/**`, `workflows/**`, `agents/registry_setup.py`, `tools/agent_eval/**`,
`tools/agent_tests/**`, `eval_sets/**`, `benchmarks/agents/**`, `package.json` (no new dependency). No new agent → no scaffold.

## 5. Tests (what each proves)

| Kind | Coverage |
|---|---|
| vitest | **testData:** same seed → same values; different testId / retry / repeat index → different; 10 000 `unique()` calls in one run have no duplicates; prefix carries the run hash; `maxLength` respected. **cleanup:** reverse order; API first, UI fallback; a failing entry → annotation + attachment, the other entries still run; `fail` mode throws. **api:** role → storageState path / anonymous empty state / config state; baseURL; host guard; dispose. **consoleGuard:** known (same path + text) vs new; other path → new; normalisation; missing baseline → warn-only note; warn vs fail vs off. **network:** records + filters; HAR shape (1.2) ; redaction of headers, form, JSON and query fields; attach on failure only (`on-failure`) vs always. **perf:** maps the evaluate payload to the field names. **a11y:** missing package → the clear error; with a fake module → AxeBuilder called with tags. **safety:** shared destructive cases = Python's verdicts; policy from env / project.yaml / unset; ActionEngine refuses a destructive click when not allowed, allows it when allowed; host guard + teardown violation. **ActionEngine:** `waitUntil` / `pollUntil` / `waitForUrl` pass and fail with tagged messages; `waitForTimeout` warns. **config builder:** `retries` auto (CI / local) + override, `fullyParallel` only with `data_isolation`, `failOnFlakyTests` auto / override, new keys in the shared cases. **MTA reporter:** `failed_step`, `cleanup_failures`. |
| pytest | Renderer golden snapshots (steps on/off, numbering, messages, secret masking, bracket safety, flows, tags + annotations on the test line, `test.use({ role })`, fallback to setup when the role is undeclared); setup `wait:` → `waitForLoadState`; validator rejects `waitForTimeout` (and ALLOWED_ACTIONS lacks it, flows still render it); re-render CLI (zero diff with legacy options; `--check` writes nothing); UIExecution: MTA source, JSON fallback, `flaky` ≠ passed, skipped stays skipped, counts, headed vs headless browser-close, `--retries=0` headed, safety env vars; traceability flaky + AC aggregation; test_suite.json stamp; ReportingAgent JSON/HTML flaky + skipped; benchmark scorer flaky (not a catch, not a stable pass, flaky rate); healing: extraction + details guard on step-wrapped blocks, sleep guard, timing suggestion, flaky after patch stays open; execution config new keys (shared cases). |
| Integration (Chromium, buggy_shop) | `test_phase4b_runtime_e2e.py`: **AC2** two workers, same create flow, no collision (§8); **AC3** deliberately flaky test end to end; **AC7** consoleGuard new vs baseline error. Plus re-run of `test_phase4_runtime_e2e.py` (AC4–6). |

## 6. Migration plan for existing generated specs

1. **Nothing is rewritten automatically.** Old specs import the same `testFixture`; the new auto fixtures only annotate
   (`console_guard: warn`, `network: on-failure`), so their pass/fail doesn't change because of 4.4. Their `beforeEach`
   `page.waitForTimeout(500)` keeps working (it's plain Playwright).
2. **Re-render on demand:** `python -m tools.test_creation.script_generator.rerender --project <p>` (E15). Specs without a
   stored plan (`raw` tier-2 fallback specs, hand-written specs) are listed and left alone.
3. **Benchmark:** re-render the 6 `bench_buggy_shop` specs with `test_steps: true` and the new `wait:` translation
   (`module_roles: false`), run `--check` first to show the diff, then run the benchmark (§7).
4. **Projects with literal setup credentials** can move to roles: add `modules[].role`, set `execution.role_auth: true`
   and `module_roles: true`, re-render. Documented in README "Auth Setup" + "Script Generation".
5. **Result consumers:** `status: "flaky"` / `"skipped"` are new values in `results[]`. In-repo consumers are updated
   (G4, G22). The frontend / API are out of my scope and only read counts they already know; see Merge notes.

## 7. Benchmark plan

Same command and data set as session 1:
`python -m tools.benchmark.run --app buggy_shop --skip-generate --no-healing --bugs BUG_01,BUG_18,BUG_21 --repeat 2 --label phase4b_after`,
compared with `benchmarks/results/2026-10-12_buggy_shop_phase4_after.json`. **Regression check:** same 61 tests (ids
equal, G18); every test that passed in both session-1 bug-free runs passes or is `flaky` (and each `flaky` one is named);
the same 11 false failures (no new failure); BUG_01/18/21 still caught. Reported: runtime median (retries add one run per
failing test; test.step adds almost nothing), flaky rate under the new definition. One benchmark run at a time, and no
pytest run at the same time (session-1 note).

## 8. Acceptance proofs

| # | How |
|---|---|
| 1 | §7 after re-rendering (step 3 of §6), plus the `--check` diff showing `test.step` + `waitForLoadState`. |
| 2 | `bench_p4b_e2e` with `data_isolation: true` (→ `fullyParallel`), `--workers=2`: one spec with 6 copies of the same create-product flow (UI form, `testData.unique('Widget')`, fixed price 9.99, `cleanup.register` delete through `api`). Each test records `{worker, product_id, name}` as an annotation. Asserts: ≥ 2 distinct workers ran concurrently (overlapping start/end times), 6 distinct product ids, each product page shows its own name, every name carries the run prefix, and after the run `GET /api/products?q=<prefix>` returns nothing (cleanup worked). **Control** in the same file: the same flow twice with one literal name within 5 s → the same product id (G13), which proves the check detects a collision. |
| 3 | A spec test that fails on attempt 0 and passes on retry (`expect(testInfo.retry).toBeGreaterThan(0)`), carrying a `tc` annotation; minimal `requirements.enabled` + `traceability.json` + `test_suite.json` in the e2e project. Asserts `flaky` in: Playwright JSON (`status: "flaky"`), MTA results, UIExecution result + `flaky` count (passed excludes it), `test_suite.json` `last_result`, `traceability.json` `latest_result.status`, ReportingAgent JSON + HTML (FLAKY pill). |
| 7 | e2e project with `console_guard: fail` and a `baseline.json` holding the real `/admin` 403 error for role `user`: test A (role user → `/admin`) **passes**; test B (role user → `/products/999999`, a 404 not in the baseline) **fails** with the new error listed. |
| 8 | Unit: validator rejects `waitForTimeout`; `ALLOWED_ACTIONS` lacks it; renderer golden snapshot has one `test.step` per plan step. Repo check: `grep -c waitForTimeout test_plans.json` = 0 for the benchmark and every re-rendered benchmark spec has `test.step` and no `waitForTimeout`. |

## 9. Mismatches with the plan / request, and proposed adjustments

| Plan / request | Adjustment | Reason |
|---|---|---|
| 4.4 `runtime/fixtures.ts` | Fixtures in `runtime/fixtures/*.ts`, wired in the existing `testFixture.ts` | Request: extend, don't replace (F5 of session 1). |
| `testData` "deterministic faker" | Seeded PRNG, no faker | G21 / E1. |
| `a11y` AxeBuilder helper | Lazy-loading stub, no dependency | Phase 7 does the checks; the request allows a stub. |
| `consoleGuard` "fails on new errors" | Default `warn`, `fail` opt-in | G12: buggy_shop's correct negative tests produce 400 console errors that no baseline crawl records. Phase 5 decides how expected 4xx document errors are treated. |
| `network` "HAR evidence" | Own redacted HAR, not `recordHar` | G16: `recordHar` stores passwords and cookies, and is written too late for a failure-only attachment. |
| `cleanup` failures "reported, never swallowed" | Reported always; fails the test only with `cleanup_failure: fail` | A passed check whose teardown failed is still a passed check; the failure is visible in the report and the MTA file. |
| 4.5 `modules[].role` → `test.use({ role })` | Behind `module_roles`, **off** by default and in the benchmark | G14: one shared session per role breaks per-session state (buggy_shop flash) under parallel workers, and stale role files break after an app restart. |
| 4.6 "ActionEngine uses web-first assertions" | Already true for every `verify*`; adds `toPass` / `expect.poll` helpers as runtime API | Exposing them to the LLM is an action-vocabulary change (Phase 5.1). |
| 4.6 "the linter flags it" | Validator rejects in plans; ScriptGeneration warns per flow; ActionEngine warns at run time | The assertion linter is Phase 5.3. |
| 4.7 retries "on in CI" | Also 1 locally (`auto`); headed always 0 | Without a local retry, `flaky` never shows up outside CI; a headed retry would reopen a window a human just closed. |
| Phase 6.6 (sleep-free timing fixes) | `apply_patch` sleep guard added now | 4.6 asks that healing not suggest sleeps; the guard is the enforceable part and costs one check. |
| Phase 3 open issues 1 + 4 expect 4.4 to set up cart state and upload files for **generated** specs | Not in this session: the fixtures are runtime support, and generated plans can't call them yet | Plans would need new vocabulary (e.g. a `{{unique:label}}` value token, a "precondition" step through `api`). That is an action-vocabulary change (Phase 5.1) plus a generator change. Until then `data_isolation` only helps specs that use `testData` themselves (hand-written / flows). |

## 10. Risks

- **R1 Runtime:** local retries rerun each failing test once. On the benchmark that's the 11 false failures (+ 13–19 in
  bug runs). Expect a noticeably slower suite; measured in §7. `retries: 0` restores today's behaviour.
- **R2 Status values:** `flaky` / `skipped` in `results[].status` are new for any consumer outside this repo's Python
  (frontend/API). Counts keep their names; `flaky` is a new count.
- **R3 Teardown host check** can fail a test that ended on a foreign host without a further action. That is the Phase 0
  intent; benchmark links are all local.
- **R4 Destructive guard at run time** refuses a click that plan filtering would also have dropped. Hand-written flows
  on a prod/unspecified project that click "Delete" will now fail — by design; the message names the policy keys.
- **R5 Classifier drift** (Python vs TS): one YAML + a shared case file tested on both sides.
- **R6 Re-render fidelity:** guarded by the zero-diff `--check` before any renderer change.
- **R7 `fullyParallel`** is only as safe as the specs: `data_isolation: true` on a project whose specs use literal data
  re-introduces collisions inside one file. Documented; off by default.
- **R8 consoleGuard false positives** in `fail` mode (4xx document loads, third-party noise). Default `warn`.

## 11. Decisions I need from you

1. **Retries default:** `auto` = 2 in CI / **1 locally** (recommended) or 0 locally (today's speed, `flaky` only in CI)?
2. **`module_roles`:** off by default and in the benchmark (recommended, G14), with an extra informative benchmark
   variant `module_roles: true` + `role_auth_max_age_minutes: 0` reported but not used for criterion 1? Or skip the
   variant to save ~25 min?
3. **consoleGuard default `warn`** (recommended, G12) — OK?
4. **New teardown failure for an unreported foreign-host navigation** (E6a) — OK, or annotate only?
5. **No new npm dependencies** (no faker, no axe-core now) — OK?
