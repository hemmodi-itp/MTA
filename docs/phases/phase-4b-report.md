# Phase 4 — Playwright Runtime Modernization: Report (session 2 of 2)

> Scope: **4.4 fixtures, 4.5 structure, 4.6 waiting, 4.7 flakiness**, as designed in `docs/phases/phase-4b-design.md`.
> Your answer to its §11 was "do what is good, but don't consume more time", so every recommendation was taken:
> retries `auto` (2 CI / 1 local / 0 headed), `module_roles` off with **no** extra benchmark variant, `console_guard:
> warn`, an unreported foreign-host navigation fails the test, no new npm dependency.
> Nothing has been committed. Session 1's report still holds where this one doesn't touch a topic.

## 1. What changed

| Task | Result |
|---|---|
| 4.4 Fixtures | `testFixture.ts` extended (`action` and `role` unchanged in use) with `testData`, `cleanup`, `api`, `consoleGuard` (auto), `network` (auto), `safety` (auto), `a11y`, `perf`; each fixture's logic is a small module in `runtime/fixtures/` (+ `runtime/destructive.ts`) with its own vitest file. **testData**: FNV-1a + mulberry32 seeded with `MTA_RUN_ID` + test id + repeat index + retry; 14-char run prefix `mta<run4><test7>`; no faker. **cleanup**: reverse order, API first / UI fallback, every failure reported (annotation `cleanup_failed`, `cleanup.json`, warning, MTA reporter `cleanup_failures`), `execution.cleanup_failure: fail` also fails the test. **api**: request context with the role's storage state and the run's baseURL; foreign hosts refused. **consoleGuard**: console errors + page errors vs `baseline.json` by (page path, normalised text); `off / warn (default) / fail`; missing baseline → warn-only with a note. **network**: request log for Phase 5 + our own redacted HAR 1.2 (no cookies, no auth headers, secret-looking form/JSON/query fields `[REDACTED]`, no response bodies), written next to the trace and attached on failure. **safety**: host guard on every page of the context (an unreported violation fails the test at teardown) + a run-time **destructive-action guard** — a TS port of `classify_step` reading the same `destructive_rules.yaml`, policy from `MTA_DESTRUCTIVE_ALLOWED` (set by UIExecution from `SafetyPolicy`) or project.yaml. **a11y**: lazy AxeBuilder wiring, clear error while `@axe-core/playwright` is absent (Phase 7). **perf**: navigation timing + FCP/LCP/CLS in baseline.json field names (Phase 7 budgets). **fullyParallel** only with `execution.data_isolation: true`; `playwright.config.ts` sets `MTA_RUN_ID` for hand runs. |
| 4.5 Structure | `spec_renderer.py`: one `await test.step("<n>. <plan step in words>", …)` per plan step (`execution.test_steps`, default true; function default false so legacy callers are byte-identical). Titles: numbered, ` — <message>` for assertions, secrets masked `•••`, never unbalanced brackets (healing counts them). Tags + `ac/tc/case/scenario` annotations stay on the one `test(` line. MTA reporter: `attempts[].failed_step`. **Session-1 open issue 2 closed:** `execution.module_roles: true` + `modules[].role` renders `test.use({ role })` instead of the literal-credential `beforeEach` (default off). New `compose.py::compose_spec` (render + login) is used by ScriptGeneration **and** the new no-LLM `rerender.py` CLI. |
| 4.6 Waiting | `waitForTimeout` removed from `ALLOWED_ACTIONS` and the prompt; `_validate_plan` rejects it (`FIXED_SLEEP_ACTIONS`, specific message). Flows still render it (warning per flow); ActionEngine keeps it with a warning + test annotation. Module `wait: N` → `await page.waitForLoadState('load')` (verified: `click()` waits for the navigation it starts to commit). ActionEngine helpers: `waitUntil` (`toPass`), `pollUntil` (`expect.poll`), `waitForUrl`, `waitForLoadState`. Healing: `apply_patch` rejects added fixed sleeps; `propose_timing_fix` returns a web-first `suggested_fix`. |
| 4.7 Flakiness | `execution.retries: auto` (2 CI, 1 local; headed always `--retries=0`, also in the 4-level CLI), `failOnFlakyTests` on in CI. **UIExecution reads per-test results from the MTA reporter file** (Playwright JSON fallback, `results_source`): `success / flaky / failed / skipped` — flaky never a pass, **Phase 1 D6 fixed** (skipped stays skipped); counts `passed / flaky / failed / skipped`. Flaky flows into `execution_results`, `traceability.json` (`LatestResult` + AC `result: flaky`, `acs_flaky`), `test_suite.json` (`last_result`, now the worst test of the spec), ReportingAgent JSON/HTML (counts + FLAKY/SKIPPED chips), benchmark scorer (flaky ≠ stable pass, ≠ catch, ≠ false failure) and healing (flaky after a patch ≠ healed). **Browser-close → skipped only in headed runs** and only for human-close errors; headless it stays `failed` with `error_kind: browser_closed`. |
| Fix found on the way | **Windows `cmd.exe` quoting** (pre-existing): `npx` is `npx.cmd`, which Windows runs through `cmd.exe`, and `subprocess` only quotes arguments with spaces — so `--grep "@smoke|@P0"` (README's own example) became a pipe: no report, EPIPE, every spec "not started". New `tools/execution/cmdline.py::resolve_cmd` double-quotes arguments with cmd metacharacters for `.cmd/.bat` targets; used by UIExecution (`_resolve_cmd`) **and** the 4-level CLI's level 3 (which passed a list but still went through `cmd.exe`, so suite greps like `(M01_BS_001\|M02_BS_001)` were affected too). Found by the AC2 e2e. |

**Files.**
- New TS: `runtime/fixtures/{testData,cleanup,api,consoleGuard,network,a11y,perf}.ts`, `runtime/destructive.ts` (+ 8 vitest files, `ActionEngine.waiting.test.ts`).
- New Python: `tools/test_creation/script_generator/{compose,rerender}.py`, `tools/execution/cmdline.py`; tests `test_spec_renderer_steps.py`, `test_plan_validator_wait.py`, `test_rerender_specs.py`, `test_ui_execution_flaky_classification.py`, `test_flaky_status_consumers.py`, `test_healing_step_wrapped.py`, `test_safety_destructive_shared_cases.py`; `tests/fixtures/destructive_cases.json` (shared pytest/vitest); e2e `tests/integration/test_phase4b_runtime_e2e.py` + `tests/e2e/phase4b/*.spec.ts`.
- Changed: `testFixture.ts`, `ActionEngine.ts`, `config/{execution,buildConfig}.ts`, `reporters/mta-reporter.ts`, `playwright.config.ts`, `tools/execution/{config,mta_results}.py`, `tests/fixtures/execution_config_cases.json`, `spec_renderer.py`, ScriptGeneration `agent.py`/`prompt.py`, UIExecution `agent.py`, Healing `tools.py`/`prompt.py`, `tools/requirements/{models,traceability}.py`, `tools/catalog/catalog_manager.py`, `tools/test_execution/reports/{report_writer,html_report}.py`, `tools/benchmark/score.py`, `tools/suite_orchestrator.py`, `contracts/artifacts/models.py`, schemas (2), templates (2), README, 3 × agent.md/agent.json, `docs/audit/current_state.md`; 6 existing tests updated to the new statuses / the moved renderer (each pinned the old behaviour this phase changes).

**Guards.** Locator validation (`count()==1`), `_flag_action_locator_type_mismatches`, `_drop_placeholder_negative_tests`, the healing tool surface (no new tool; `apply_patch` gained a check), the Phase 0 rails (plan filtering unchanged; run time **stricter**: destructive guard + teardown host check) and session 1's credential handling (step titles mask secrets, the HAR is redacted, `module_roles` removes literal credentials from specs) are kept or strengthened.

## 2. Tests

| Suite | Session 1 end | Now |
|---|---|---|
| `npx vitest run` | 89 passed (7 files) | **174 passed (15 files)** |
| `python -m pytest tests/unit` | 1,792 passed | **1,885 passed, 0 failed** (8 min 46 s); +1 CLI test added after it, run with the files touched last: 42 passed |
| `pytest tests/integration/test_phase4b_runtime_e2e.py` (real Chromium, buggy_shop) | — | **3 passed** (34.4 s; again 39.9 s after the final `cmdline.py` move) |
| `pytest tests/integration/test_phase4_runtime_e2e.py` (session-1 AC 4–6) | 4 passed | **4 passed** (94.4 s) |
| `npx tsc --noEmit` | only the pre-existing alterDomusInvest error | unchanged |

```
$ npx vitest run
 Test Files  15 passed (15)
      Tests  174 passed (174)

$ python -m pytest tests/integration/test_phase4b_runtime_e2e.py -v
test_ac2_two_parallel_workers_same_create_flow_no_collision PASSED
test_ac3_flaky_test_is_flaky_end_to_end PASSED
test_ac7_console_guard_new_error_fails_baseline_error_does_not PASSED
============================= 3 passed in 34.41s ==============================

$ python -m pytest tests/integration/test_phase4_runtime_e2e.py -v
test_unsharded_run_roles_reporters_and_evidence PASSED
test_two_shards_merged_equal_the_unsharded_totals PASSED
test_ci_style_shards_then_merge_run PASSED
test_suite_by_tag_and_grep PASSED
======================== 4 passed in 94.38s (0:01:34) =========================
```

```
$ python -m pytest tests/unit -q --durations=12
1885 passed in 526.38s (0:08:46)
$ python -m pytest tests/unit/test_suite_orchestrator_grep.py tests/unit/test_ui_execution_flaky_classification.py     tests/unit/test_ui_execution_phase4.py tests/unit/test_ui_execution_agent_install_checks.py   # after the cmdline.py move
42 passed in 15.47s
```
An earlier full run (before the last fixes) had 1,851 passed / 2 failed: a ScriptGeneration test that patched
`render_spec_from_plan` in its old module (re-targeted to `compose.py`) and `test_playwright_executor.py::
test_wrong_password_blocks_every_plan`, which passed alone and in the final run (load flakiness, unrelated).

New unit coverage — **vitest:** testData (determinism, 10 000 distinct prefixes / values, maxLength, email, ranges), cleanup (reverse order, API→UI fallback, failures reported and others still run, lazy api), api (host guard, role → storage state), consoleGuard (path+text baseline diff, ANSI/whitespace, warn/fail/off, missing / invalid baseline → warn-only), network (log, filters, header/form/JSON/multipart/query redaction, HAR 1.2 without secrets, attach policy), a11y (missing package error, AxeBuilder wiring), perf (field mapping, nulls), destructive (22 shared cases = Python verdicts, policy env/project/none, ActionEngine refuses/permits clicks and navigations), ActionEngine waiting (toPass, poll, waitForUrl, waitForTimeout warning, reported host violation), config builder (retries auto/CI/override, headed 0, failOnFlakyTests, fullyParallel gating, new shared cases), MTA reporter (failed_step, cleanup_failures). **pytest:** renderer golden snapshots (steps + setup, role head, legacy unchanged, tags/annotations on the test line, step titles, secret masking, bracket safety, healing extraction on the golden spec), validator rejects `waitForTimeout` (flows still render it), rerender (zero diff, `--check` writes nothing, `.bak`, role rendering, exit codes), UIExecution (MTA source + JSON fallback, flaky ≠ passed, skipped stays, timedOut→failed, headed/headless browser-close, `_merge_runs`, effective retries, `--retries=0` headed, safety env vars, cmd.exe quoting), traceability / test_suite / report JSON+HTML / scorer flaky handling, healing on step-wrapped specs (patch inside a step, details guard, sleep guard ×3, existing sleep allowed, web-first timing suggestion, flaky after patch stays open), shared destructive cases.

## 3. Acceptance criteria

| # | Criterion | Command | Result |
|---|---|---|---|
| 1 | Existing generated specs still pass after re-rendering with `test.step` (no regression vs `phase4_after`) | `python -m tools.test_creation.script_generator.rerender --project bench_buggy_shop` then `python -m tools.benchmark.run --app buggy_shop --skip-generate --no-healing --bugs BUG_01,BUG_18,BUG_21 --repeat 2 --label phase4b_after` | **Met.** Re-render: 6/6 specs, 353 `test.step` (= every plan step of the 61 tests), 0 `waitForTimeout`. Fidelity proof first: re-rendering with the legacy options changed exactly one line per spec (`page.waitForTimeout(500)` → `page.waitForLoadState('load')`). Benchmark: same 61 test ids; **per-test outcomes identical** to session 1 on both bug-free runs (50/61, 49/61), the same 11 false failures, the same flaky test, 3/3 bugs caught (§4). |
| 2 | Two parallel workers, same create flow, no collisions | `pytest tests/integration/test_phase4b_runtime_e2e.py::test_ac2_…` | **Met.** `data_isolation: true` → `fullyParallel`; 6 copies of the UI create-product flow in one file ran on workers 0 and 1 **concurrently** (e.g. +0–553 ms on worker 0 and +19–584 ms on worker 1) → 6 distinct product ids (24–29), 6 distinct names (`mtackwozvdgd4a-widget-1`, …, one run part `mtackwo`), each product page showing its own name; `cleanup` deleted all six through `api` (none left via `/api/products?q=<prefix>`), no `cleanup_failures`. Control: the same literal name twice within 5 s returned the **same** product id — the collision buggy_shop really produces without `testData`. |
| 3 | A deliberately flaky test is `flaky` end to end | `…::test_ac3_…` | **Met.** Playwright JSON `status: "flaky"`; MTA results `flaky`, attempts `[failed, passed]`; UIExecution result `flaky`, `flaky: 1`, `passed: 1` (only the stable test), `results_source: mta_results`, `retries: 1`; `traceability.json` `latest_result.status: flaky`, AC-90.1 `result: flaky`, `acs_flaky: 1`; `test_suite.json` `last_result: flaky`; ReportingAgent JSON `flaky: 1` and HTML FLAKY chip + "⚠ Flaky" block. |
| 7 | consoleGuard fails on a new console error, not on a baseline one | `…::test_ac7_…` | **Met.** `console_guard: fail`, baseline holds the real user `/admin` 403 error: the `/admin` test **passed** (`knownErrors()` non-empty); the `/products/999999` test **failed** with `consoleGuard: 1 new console error(s) not in baseline.json: - [console] /products/999999: Failed to load resource: … 404 (Not Found)`, annotation `console_new_error`, redacted `network.har` attached (no session id, no password in any report). |
| 8 | No `waitForTimeout` in LLM plans; `test.step` per plan step | `pytest tests/unit/test_plan_validator_wait.py tests/unit/test_spec_renderer_steps.py` | **Met.** Not in `ALLOWED_ACTIONS` or the prompt; validator rejects it; golden snapshot has one `test.step` per plan step; benchmark `test_plans.json` and re-rendered specs contain no `waitForTimeout`. |
| 4–6 | (session 1) JUnit + MTA output, per-role auth, shards + merge | `pytest tests/integration/test_phase4_runtime_e2e.py` | **Still met** — 4 passed, with retries now on (the deliberately failing test runs twice and is still `failed`, counts 9/1 unchanged). |

## 4. Benchmark — before / after

Same data set and command as session 1 (Phase 3 quick suite, M03 + M04, 61 tests, in the gitignored
`bench_buggy_shop`), after re-rendering. "Before" = `benchmarks/results/2026-10-12_buggy_shop_phase4_after.json`.

| KPI | Session 1 after | Session 2 after |
|---|---|---|
| Tests executed / ids | 61 | 61, **identical ids** |
| Bug-free run 1 / run 2 passed | 50 / 49 | 50 / 49 |
| Per-test outcome, both bug-free runs | — | **identical** to session 1 (49 stable passes all still pass) |
| False-failure rate | 18.0 % (11 tests) | 18.0 % (**same 11 tests**) |
| Flaky rate (new definition: retry-flaky or differs across runs) | 1.6 % (1 test) | 1.6 % (**same test**) |
| Seeded-bug detection | 3 / 3 | 3 / 3 |
| Failing tests BUG_01 / BUG_18 / BUG_21 | 18 / 13 / 13 | 18 / 13 / 13 |
| Suite run time, median of 5 runs | 208.6 s | **312.3 s (+49.7 %)** |
| Total runtime | 1,124.4 s | 1,720.5 s |
| LLM calls / cost | 0 / $0 | 0 / $0 |
| Results source / retries | Playwright JSON / 0 | MTA reporter / 1 |

Files: `benchmarks/results/2026-10-12_buggy_shop_phase4b_after.{json,md}`.

- **+50 % run time is the local retry**: every failing test runs twice (the 11 false failures in clean runs, 13–18 in
  bug runs); `test.step` and the auto fixtures add almost nothing on passing tests. `execution.retries: 0` restores
  session-1 speed; CI uses 2.
- **The known flaky test is not timing:** `AC-05.1.1 Quantity range nominal (50) is accepted` failed **both** attempts
  in clean run 2 (`failed_step: 4. Verify "add_to_cart_form_errors" is hidden`), so a retry does not recover it and
  it is still counted as an outcome flip across runs, not as `flaky`. buggy_shop keeps carts per **username**, so tests
  of one user share a cart — a data-isolation problem (open issue 2), not a wait problem.
- No test became `flaky` on the benchmark: none of the 11 false failures passes on a retry; they are the Phase 3
  oracle problems (native validation texts, vague "violate" cases) that Phase 5 addresses.

## 5. Deviations from the plan / request

| Plan / request | Done | Why |
|---|---|---|
| `runtime/fixtures.ts` | Modules in `runtime/fixtures/*.ts`, wired in the existing `testFixture.ts` | Extend, don't replace |
| testData "deterministic faker" | Seeded PRNG, no dependency | Uniqueness + determinism is what isolation needs |
| a11y AxeBuilder helper | Lazy wiring, no dependency | Checks are Phase 7 |
| consoleGuard "fails on new errors" | `warn` default, `fail` opt-in | buggy_shop's correct negative tests log 400 document errors that no baseline crawl records |
| network "HAR evidence" | Own redacted HAR, not `recordHar` | `recordHar` stores passwords/cookies and is written after test-scoped fixtures |
| cleanup failures "never swallowed" | Always reported; fails the test only with `cleanup_failure: fail` | A passed check with a failed teardown is still a passed check; the failure is visible everywhere |
| `modules[].role` → `test.use({ role })` | Behind `module_roles`, off by default and in the benchmark template (roles are declared there, one switch away) | One shared role session leaks buggy_shop's per-session flash message between parallel tests; the app restarts per bug. No extra benchmark variant (your "don't consume more time") |
| "ActionEngine uses web-first assertions" | Already true; `toPass` / `expect.poll` helpers added as runtime API | Exposing them to the LLM is Phase 5.1 vocabulary |
| "the linter flags it" | Validator rejects in plans; flows warn; ActionEngine warns | The assertion linter is Phase 5.3 |
| retries "on in CI" | Also 1 locally, 0 headed | Otherwise `flaky` never appears locally; a headed retry would reopen a window a human closed |
| (Phase 6.6) | `apply_patch` sleep guard added now | 4.6's "healing must not suggest sleeps" needs an enforceable check |
| (not in plan) | `test_suite.json` `last_result` = worst test of the spec | It used to be the *last* test's result, so a spec with a failing test could read "passed" |
| (not in plan) | Windows `cmd.exe` quoting fix | `--grep` with `|` produced no report on Windows |

## 6. Open issues

1. **Generated specs can't use `testData` / `cleanup` yet.** Plans have no vocabulary for "a unique value" or "an API
   precondition", so `data_isolation` only helps specs that use the fixtures themselves (hand-written, flows). Phase 3
   open issues 1 + 4 (cart state, upload fixtures) wait for that (Phase 5.1 vocabulary + generator).
2. **Shared per-user state on buggy_shop** (carts per username, flash per session) is the likely cause of the one
   flaky benchmark test; per-test users or API-reset preconditions need open issue 1.
3. **Unit-suite runtime** varies with machine load: 8 min 46 s in the final run, 27 min 40 s in an earlier one on the
   same code (the slowest tests are the real-browser Phase 2 crawl / executor tests, 20–60 s each, not this phase's).
4. **Run time +50 % locally** with `retries: auto` (one extra run per failing test). Set `execution.retries: 0` where
   speed matters more than flaky detection.
5. **`module_roles`** is built and unit/rerender-tested but not benchmarked (see §5). Before turning it on for an app,
   check for per-session server state and set `role_auth_max_age_minutes: 0` if the app restarts between runs.
6. **`consoleGuard: fail`** would fail buggy_shop negative tests (400 document loads). Phase 5 should decide how
   expected 4xx document errors are treated (e.g. ignore the main document's status error when the test expects it).
7. **4-level CLI** levels 1/2/4 (`tools/suite_orchestrator.py::_run`) still run a `shell=True` string; they pass no
   grep, so the `|` problem doesn't reach them, but paths with `(`/`)` are left as they were (pre-existing).
8. **git status shows the 16 untouched `schemas/*.json` as modified** after `export_schemas`: `core.autocrlf=true`
   flags them, but their blob hashes equal HEAD (`git diff` is empty) — committing changes nothing there. Only
   `mta_results.v2` and `traceability.v2` really changed.
9. Pre-existing, unchanged: `tests/unit/test_playwright_executor.py::test_wrong_password_blocks_every_plan` failed once
   under load and passed alone (17.7 s) and in the final run; the alterDomusInvest `tsc` error.

## 7. Merge notes

Shared files touched (all additive — new keys / sections, no rename or removal):
- **README.md:** "Script Generation" (vocabulary without `waitForTimeout`; new "Rendered spec shape" subsection);
  "Self-Healing" (flaky after patch; Phase 4 additions); "Execution" (command `--retries=0`, results/statuses
  paragraph, two table rows replaced, new "Runtime fixtures" subsection); "Playwright configuration" (rows
  `retries` / `failOnFlakyTests` / `fullyParallel` replaced, new-keys paragraph); "Suite Manifest" (`last_result`).
- **schemas/:** `mta_results.v2.schema.json` (optional `failed_step`, `cleanup_failures`) and
  `traceability.v2.schema.json` (enum gains `flaky`). Others byte-identical (see open issue 8).
  `python -m contracts.artifacts.export_schemas --check` passes.
- **contracts/artifacts/models.py:** two optional fields on `MtaAttempt` / `MtaTest`.
- **package.json / package-lock.json, workflows/*.yaml, agents/registry_setup.py, api/**, frontend/**:** not touched.
- **Result values:** UIExecution `results[].status` can now be `flaky` / `skipped` (was `success` / `failed`), and
  results gain `flaky`, `results_source`, `retries`, `failed_step`, `cleanup_failures`, `error_kind`. The Phase 9 / UI
  branches should treat unknown statuses as non-passing and may show the new `flaky` count.
- **Prompts:** ScriptGeneration (one line replaced: no fixed sleep) and Healing (two rules added). Any branch editing
  these prompts should keep them.
- **Templates:** `aAprojectTemplate/project.yaml` (commented session-2 keys + `modules[].role` comment);
  `benchmarks/apps/buggy_shop/mta_project/project.yaml.tmpl` (`module_roles: false`, `role:` on M02–M06).
- **Tests:** `tests/fixtures/execution_config_cases.json` gained 8 keys per case + 3 cases (both resolvers read it);
  new `tests/fixtures/destructive_cases.json`.
- After merging: `npm install` is not needed for this session (no dependency change). Re-render existing projects on
  demand with `python -m tools.test_creation.script_generator.rerender --project <p> --check`.
