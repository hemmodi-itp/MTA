# Phase 4 — Playwright Runtime Modernization: Report (session 1 of 2)

> Scope of this session: **4.1, 4.2, 4.3, 4.8, 4.9** and their tests, as designed in `docs/phases/phase-4-design.md`
> (decisions D1–D9; your answer to §10 was "do the best according to you", so every recommendation was taken).
> 4.4 (fixtures), 4.5 (`test.step` + renderer), 4.6 (waiting) and 4.7 (flaky classification) are the next session.
> Nothing has been committed.

## 1. What changed

| Task | Result |
|---|---|
| 4.1 Upgrade | `@playwright/test` pinned to **`1.64.0`** (exact; npm `latest`), recorded in `docs/audit/current_state.md`. Features checked in the 1.64.0 package: test `tag`/`annotation`, `toMatchAriaSnapshot`, `page.clock`, `failOnFlakyTests`, `blob` + `merge-reports`, reporter `outcome()` = `flaky`. The Chromium build it needs (rev. 1248) was already installed. |
| 4.2 Config | `playwright.config.ts` is now a thin wrapper around `buildPlaywrightConfig()` (`runtime/config/buildConfig.ts`), which reads the new **`execution:`** block of project.yaml (`yaml` 2.9.1). It provides: projects matrix (`chromium` always; `firefox`, `webkit`, `pixel-7`, `iphone-14`; profile `smoke` → chromium only); `trace`/`video: retain-on-failure`, `screenshot: only-on-failure`; `testIdAttribute` (default `data-testid`); `locale`/`timezoneId`; reporters list, json, html, **junit**, **MTA reporter**, **blob** (shards). `forbidOnly: !!CI` was already there; the base URL still fails fast (Phase 0 confirmed). `retries: 0` and no `fullyParallel` are unchanged until 4.7 / 4.4. Python resolves the same block (`tools/execution/config.py`), and both sides are tested against one shared case file. |
| 4.2 MTA reporter | `runtime/reporters/mta-reporter.ts` → `reports/mta/<ts>.mta_results.json` (contract `mta_results` v2, `schemas/mta_results.v2.schema.json`). Per test: test id, title, spec, project, tags, `tc_id` / `ac_ids` / `case_id` / `scenario_id`, a status that keeps `flaky` apart, attempts, attachment paths. `tools/execution/mta_results.py` converts it for `traceability.json` (contract-tested). |
| 4.3 Auth per role | `tools/auth/role_states.py` logs every `auth.roles` role in **before** Playwright starts. It reuses Phase 2's `open_role` and writes `.auth/<role>.json`. Triggered by `execution.role_auth: true`, `--auth-setup` (now also roles) or `python -m tools.auth.role_states`. The `role` option fixture (`test.use({ role: 'admin' })`) overrides `storageState`; anonymous roles get an empty state. Single-identity projects are unchanged. Credentials never enter the test runner, and setup-step values are now redacted in logs (`playwright_scanner.py`). |
| 4.8 Shards | `--shards N` runs N local shards plus `merge-reports` (`playwright.merge.config.ts`, reporters only) into the normal json / html / junit / mta outputs, with one index entry. `--shard i/n --run-id R` runs one CI shard (normal reports + blob); `--merge-reports R` merges. Headed runs and healing re-runs never shard. |
| 4.9 Tags | `--grep` / `--grep-invert` (main.py, UIExecution). With `execution.suite_mode: grep`, `test_suites/*.json` → one bounded grep over spec ids (file name + describe title, so pre-Phase-1 specs work), plus new optional `tags` / `grep` keys. The 4-level CLI's level 3 uses it too when the suite has tags, or when `individual/` is absent (it used to find nothing). The default `files` mode is unchanged. |
| Fixes found on the way | (a) `--output` was the HTML report folder, which the HTML reporter empties, so failure screenshots/traces/videos were deleted → now `reports/test-results/<ts>/`. (b) Python live locator validation checked `data-testid` while the runtime used `data-test` → both now use `execution.test_id_attribute` (`count() == 1` unchanged). sauceLabs migrated to `data-test` explicitly. |

**Files.**
- New: `application_assets/_shared/runtime/{config/{execution,buildConfig,projectYaml}.ts, auth/roles.ts, reporters/mta-reporter.ts}` (+ 3 vitest files), `playwright.merge.config.ts`, `tools/execution/{config,suite_grep,mta_results,shards,merge_reports}.py`, `tools/auth/role_states.py`, `schemas/mta_results.v2.schema.json`, `tests/fixtures/execution_config_cases.json`, 10 pytest files, `tests/integration/test_phase4_runtime_e2e.py` + `tests/e2e/phase4/*.spec.ts`.
- Changed: `package.json` / `package-lock.json`, `playwright.config.ts`, `runtime/fixtures/testFixture.ts` (`role`; `action` untouched), `ui_execution/agent.py`, `tools/suite_orchestrator.py`, `tools/project_manifest.py`, `tools/playwright_scanner.py` (log redaction), `locator_resolve.py` + ScriptGeneration / Healing callers (test-id attribute), `contracts/artifacts/{models,registry,paths,boundary}.py`, `main.py`, templates (`aAprojectTemplate`, `buggy_shop` tmpl), `sauceLabs/project.yaml`, README, agent.md / agent.json, audit, `requirements-dev.txt` (+`hypothesis`).
- No new agent, so no scaffold, registry or workflow change.

**Guards.** Locator validation (`count() == 1`), `_flag_action_locator_type_mismatches`, `_drop_placeholder_negative_tests`, the healing tool surface and the Phase 0 rails are untouched. Validation now checks the attribute the runtime really uses; log redaction only removes data.

## 2. Tests

| Suite | Before | After |
|---|---|---|
| `npx vitest run` | 49 passed (4 files) | **89 passed (7 files)** |
| `python -m pytest tests/unit` | 1,629 passed | **1,792 passed, 0 failed** (7 min 44 s). The count also grows with the per-artifact contract test, which is parametrised per file of the copied benchmark project |
| `python -m pytest tests/integration/test_phase4_runtime_e2e.py` (real Chromium, buggy_shop) | — | **4 passed** (129.5 s) |

New unit tests:
- **vitest:** config builder (shared cases, matrix/profile → projects, device descriptors, MTA_PROJECTS override, testId/locale/timezone, storageState, CI flags, reporters incl. blob-only shards, merge config without baseURL); MTA reporter (status mapping incl. flaky/timedOut/interrupted, TC/AC/case/scenario linking, bounded ANSI-free errors, attachments without bodies, atomic write); roles (file names, strategies, missing-file / undeclared-role messages).
- **pytest:** `execution:` resolution (+ shared cases, manifest, sauceLabs migration); suite → grep (bounded ids, ordinals, per-entry grep, exact tags, every grep re-checked with Node's RegExp); MTA loader → `apply_results` contract; shard planning / blob collection / merge env; UIExecution (projects, `--output` ≠ HTML folder, report env vars, grep, no-match → skipped, missing-browser message, local shards + merge + single index entry, CI shard + `merge_run`, headed / healing never shard, suite grep mode, role pre-step once per execute and off by default); role pre-step (capture / reuse / force / failed login listed / storageState check / nothing secret logged); setup-step redaction; test-id attribute in Python validation; 4-level CLI level 3; main.py `--auth-setup` with roles and `--merge-reports`.

## 3. Acceptance criteria (this session's subset)

| # | Criterion | Command | Result |
|---|---|---|---|
| 1 | Existing generated specs still pass (no regression vs Phase 3) | `python -m tools.benchmark.run --app buggy_shop --skip-generate --no-healing --bugs BUG_01,BUG_18,BUG_21 --repeat 2 --label phase4_{before,after}` (before = pristine `9a382d7` export, after = this branch) | **Met.** Same 61 tests; per-test results identical on both bug-free runs (50/61, 49/61, the same 11 false failures and the same flaky test); 3/3 bugs still caught. Details in §4. |
| 4 | JUnit XML + MTA reporter output; MTA output links tests to TC/AC | `pytest tests/integration/test_phase4_runtime_e2e.py::test_unsharded_run_roles_reporters_and_evidence` | **Met.** JUnit: 10 tests / 1 failure. `mta_results` validates against its contract. `admin reaches the admin page` → `tc_id P4_TC_001`, `ac_ids [AC-06.1]`, tags, project `chromium`. The deliberately failing test keeps **screenshot, trace and video** on disk after the HTML report is written (fix (a)). No password in json / junit / mta. |
| 5 | Per-role auth: ≥ 2 roles + anonymous on the benchmark app | same test | **Met.** Role pre-step: `user` captured, `admin` captured, `guest` anonymous, `failed: []`. Admin → `/admin` 200 + `getByTestId('nav-admin')` (default `data-testid`); user → `/admin` 403 "Access denied"; user → `/products` without logging in again; guest → redirected to `/login?next=…`. |
| 6 | 2 shards + merge = unsharded totals | `…::test_two_shards_merged_equal_the_unsharded_totals`, `…::test_ci_style_shards_then_merge_run` | **Met.** Unsharded 9 passed / 1 failed; `shards: 2` → 2 blob zips → merged 9 / 1, identical per-test statuses, merged MTA totals and JUnit counts = 10. CI style: shard 1/2 + 2/2 with `run_id`, then `merge_run` → 10 tests. |
| — | Suites by tag | `…::test_suite_by_tag_and_grep` | `test_suites/roles_suite.json` (`tags: [@roles]`) → exactly the 4 role tests in one process; `--grep @smoke` → the 2 smoke tests. |

Criteria 2 (data collisions), 3 (flaky end to end), 7 (consoleGuard) and 8 (no `waitForTimeout`, `test.step`) depend on
4.4–4.7 → next session.

## 4. Benchmark — before / after

Phase 3 quick suite (M03 + M04, 61 tests), copied unchanged from the main checkout into the gitignored
`application_assets/projects/bench_buggy_shop/`. Reduced to 2 bug-free runs + the 3 bugs this suite catches
(time box 13:45). "Before" ran on a pristine `git archive` of `9a382d7` (inside the gitignored `.aqp_artifacts/`)
with its own `node_modules` (Playwright 1.61); "after" ran on this branch (1.64).

| KPI | Before (`9a382d7`, Playwright 1.61) | After (Phase 4, 1.64) |
|---|---|---|
| Tests executed | 61 | 61 |
| Bug-free run 1 / run 2 passed | 50 / 49 of 61 | 50 / 49 of 61 |
| False-failure rate (bug-free) | 18.0 % (11 tests) | 18.0 % (**same 11 tests**) |
| Flaky rate (2 bug-free runs) | 1.6 % (1 test) | 1.6 % (**same test**) |
| Per-test status on both bug-free runs | — | **identical** to before |
| Seeded-bug detection (3 evaluated) | 3 / 3 (BUG_01, BUG_18, BUG_21) | 3 / 3 |
| Failing tests with the bug on: BUG_01 / BUG_18 / BUG_21 | 19 / 13 / 13 | 18 / 13 / 13 |
| Suite run time, median of 5 runs | 199.4 s | 208.6 s (**+4.6 %**) |
| Total runtime | 6,288.5 s (stalled, see below) | 1,124.4 s |
| LLM calls / cost | 0 / $0 | 0 / $0 |

Files: `benchmarks/results/2026-10-12_buggy_shop_phase4_{before,after}.{json,md}`.

- **BUG_01 19 → 18:** one extra failure before (`AC-03.1.2 … empty or blank name is rejected`) did not repeat after.
  It passes on all 4 bug-free runs and is not about the 50-character boundary that BUG_01 breaks, so it is run-to-run
  noise, not a change in what the suite detects. BUG_01 is caught by the same boundary tests in both runs.
- **+4.6 % run time** is the price of `retain-on-failure` video and trace, which now record every test and keep them
  for failures, plus the JUnit and MTA reporters. `execution.video: off` / `trace: off` per project turns that off.

Notes:
- **Total runtime** is not comparable. The "before" process stalled for ~1.5 h between its clean runs (12:25) and
  BUG_01 (13:57); the most likely cause is the machine sleeping, since no code changed in between. Use the per-run
  median instead.
- An earlier full 22-bug "before" run reached BUG_08 before I stopped it for the time box: BUG_01 caught (18 failing
  vs 11–12 bug-free), BUG_02…08 not caught (11 failing, the bug-free set). That is consistent with the Phase 3 report.
- The 1 flaky test (1.6 %) is `AC-05.1.1 Quantity range nominal (50) is accepted`, already flaky before Phase 4.

## 5. Deviations from the plan / request

| Plan / request | Done | Why |
|---|---|---|
| 4.3 setup project / globalSetup | Python pre-step (`role_states.py`, Phase 2's `open_role`) + TS `role` fixture | A setup project is a test: its `fill(password)` would be recorded in traces and reports (design D7) |
| `fullyParallel: true` | Still off | Only with 4.4 data isolation, as requested |
| MTA reporter writes into `traceability.json` (plan) | Separate `mta_results.json` + loader + contract test | Request wording; traceability stays Python-owned. UIExecution still folds the Playwright JSON (switch together with 4.7's flaky status) |
| 4.9 "spec ids → tags" | Spec ids → bounded grep on file name / describe title | Works for every existing spec without re-rendering |
| `retries`, `failOnFlakyTests` | Untouched (both verified available) | 4.7 |
| Project template `role_auth: true` (design §3) | `role_auth: false` + comment in `aAprojectTemplate` (its roles are commented out); `true` in the buggy_shop template | Avoids a "no roles declared" warning on every run of a fresh project |
| (not in plan) | `--output` / HTML-folder fix; Python/TS test-id alignment; setup-value log redaction | Needed for retain-on-failure evidence, honest locator validation, and "credentials never in logs" |
| Orchestrator "no new additions" bypass for `--grep` | Not added | The guard only applies to a step named `execution`, and every workflow uses `ui_execution`, so it never triggers |

## 6. Open issues

1. **Role states are reused by age** (`role_auth_max_age_minutes`, default 30). An app restart that drops server
   sessions within that window needs `--auth-setup` / `--force`. buggy_shop's benchmark restarts the app per bug, but
   its generated specs don't use roles yet.
2. **Renderer emits no `test.use({ role })` yet.** Module logins are still rendered `beforeEach` steps with literal
   values (Phase 3 open issue 3). This is a 4.5 change: modules[].role → `test.use({ role })`.
3. **UIExecution still counts Playwright `flaky` as a pass** and maps `skipped` → `failed` in `status` (Phase 1 D6).
   The MTA reporter already has the right statuses. Switch in 4.7.
4. **`npm audit`** reports moderate/high advisories in vitest's dependencies (`@vitest/mocker`, `nanoid`, `postcss`).
   They predate this phase and are dev-only. Not changed (vitest is outside this phase).
5. **Retained traces contain session cookies** (not credentials) under the gitignored `reports/` tree.
6. The scanner still records a `testid` value from `data-testid` / `data-test` / `data-qa` without the attribute name.
   A key whose attribute differs from the project's is now **excluded** by validation instead of failing at run
   time. Recording the attribute is a discovery change for a later phase.
7. `tests/e2e/phase4/*.spec.ts` import the fixture by the path they will have after the integration test copies them
   into `bench_p4_e2e`, so editors flag the import in place.
8. Pre-existing, unchanged: the alterDomusInvest spec syntax error (Phase 1 open issue 8) is the only `tsc` error.

## 7. Merge notes

Shared files touched (all additive):
- **README.md:** manifest example gains an `execution:` block; "Execution" (command, outputs table, MTA reporter,
  tags / suites, shards); "Playwright configuration" table rewritten for the new keys (the old values it listed are
  all still true or listed as changed); "Modular Execution" level-3 paragraph; "Running the Platform" (new flags);
  "Auth Setup" §3 roles; testing command for the e2e test; one browser-binary row and the flaky row reworded.
- **schemas/:** new file `mta_results.v2.schema.json` only. The other schema files were regenerated byte-identical
  except for line endings and then restored. `python -m contracts.artifacts.export_schemas --check` passes.
- **contracts/artifacts/:** new `mta_results` artifact (model, registry entry, path glob, `ui_execution`/`execution`
  boundary entry). No existing model changed.
- **workflows/*.yaml, agents/registry_setup.py, api/**, frontend/**:** not touched.
- **package.json / package-lock.json:** `@playwright/test` `^1.49.0` → `1.64.0`, new devDependency `yaml` `2.9.1`.
  Phase 9 / UI branches that change `package.json` should rebase onto these two lines.
- **main.py:** new flags `--grep`, `--grep-invert`, `--shard`, `--shards`, `--run-id`, `--merge-reports`;
  `--auth-setup` moved into `_auth_setup()` (same behaviour + roles).
- **requirements-dev.txt:** `+ hypothesis>=6.0` (Phase 3 tests already needed it).
- **Projects:** `application_assets/projects/sauceLabs/project.yaml` gains `execution.test_id_attribute: data-test`.
  `aAprojectTemplate` and the buggy_shop template gain an `execution:` block.
- After merging, run `npm install` (Chromium rev. 1248 for 1.64 if it is not cached: `npx playwright install chromium`).
