# Phase 4 — Playwright Runtime Modernization: Design Note (session 1 of 2)

> Inputs checked against the code on 2026-10-12 at `9a382d7` ("Phase 3 done"), branch `mta-v3/phase-4`.
> **Scope of this session:** 4.1 (upgrade + pin), 4.2 (config, reporters), 4.3 (auth per role), 4.8 (shards +
> merge), 4.9 (suites by tag), with their tests. **Deferred to the next session:** 4.4 fixtures, 4.5 `test.step` +
> renderer, 4.6 waiting, 4.7 flaky classification. Acceptance criteria 2, 3, 7 and 8 belong to those tasks; this
> session proves 1, 4, 5 and 6.
> Where this note and the plan disagree, §8 lists the change and why.

---

## 1. Verified facts (plan assumption → what the code does)

| # | Assumption | Reality (file:line at `9a382d7`) | Consequence |
|---|---|---|---|
| F1 | Upgrade from an old Playwright | `package.json` has `"@playwright/test": "^1.49.0"`; **1.61.0** is installed. npm `latest` = **1.64.0** (published 2026-10-07); 1.63.0 was published 2026-09-04. | Pin `1.64.0` exactly (D1). |
| F2 | Features exist | Checked in the 1.64.0 tarball: `TestDetails.tag/annotation` (`types/test.d.ts`), `toMatchAriaSnapshot` (26 hits), `page.clock` (`playwright-core` types), `failOnFlakyTests` (config + CLI `--fail-on-flaky-tests`), `blob` reporter + `merge-reports` command (`lib/program.js:108`), reporter `TestCase.outcome()` → `'flaky'`, project `dependencies`/`teardown`. `node_modules/playwright/lib/program.js` still exists, so the install check (`ui_execution/agent.py:1329`) keeps working. | All features the phase needs are present. |
| F3 | Config has old defaults | `playwright.config.ts`: `retries: 0`, `trace`/`video: 'on-first-retry'` (never record, because retries are 0), `testIdAttribute: 'data-test'`, reporters list/json/html. `forbidOnly: !!process.env.CI` **already present**. | Only the missing parts change. |
| F4 | No localhost fallback (P0) | **Confirmed.** `runtime/baseUrl.ts::resolveBaseUrl` throws when nothing resolves; no `localhost:3000` anywhere in config/runtime. But the config throws **at load time**. `npx playwright merge-reports` loads a config for its reporters, so it would throw too. | Merging uses a separate reporters-only config (D8). |
| F5 | Runtime fixture | One file: `application_assets/_shared/runtime/fixtures/testFixture.ts` (`action` fixture, PAGE_REGISTRY, host guard). The plan's `runtime/fixtures.ts` / `runtime/reporters/` mean `application_assets/_shared/runtime/…`. | New TS lives under `application_assets/_shared/runtime/` (vitest already covers `runtime/**/*.test.ts`). |
| F6 | `--project` is configurable | UIExecutionAgent hard-codes `--project=chromium` (`agent.py:405`, and `:668` in the headless re-run). SuiteOrchestrator passes no `--project`. | Python must know the enabled project names (D4). |
| F7 | — (not in plan) | **Pre-existing bug:** UIExecutionAgent passes the same folder as `--output` (`agent.py:411`) and as the HTML report folder (`:387`). Playwright 1.6x prints "Configuration Error: HTML reporter output folder clashes with the tests output folder" and **clears the folder when it writes the report**, deleting screenshots/traces/videos of failed tests. | Must be fixed, or `retain-on-failure` evidence is deleted anyway (D5). |
| F8 | Test-id attribute is only a config value | Python live validation uses `get_by_test_id()` with Python Playwright's default **`data-testid`** (`script_generator/locator_resolve.py:39-40`, `healing/tools.py:308`); the TS runtime uses **`data-test`**. The scanner stores a `testid` value from `data-testid` **or** `data-test` **or** `data-qa` (`playwright_scanner.py:163-167`) without the attribute name. `testid` locator entries exist in AWS_Test (29), AWS_World (3), Blog_Writing_Agent (1; Streamlit: `data-testid`) and sauceLabs (1; saucedemo: `data-test`). | Today AWS/Streamlit testid keys pass Python validation and then fail at run time. The attribute must be per project and the **same** in Python and TS (D3, §6). |
| F9 | Auth per role is new | Phase 2 already parses `auth.roles` (`tools/discovery/deep/config.py::RoleConfig`; strategies `credentials`, `storageState`, `setup`, `anonymous`) and opens a context per role (`deep/roles.py::open_role`, which reuses `auth/live_login.perform_login` and `playwright_scanner.execute_setup_steps`). `tools/auth/auth_setup.py` handles the single-identity `auth:` block only. | Reuse `open_role` to write `.auth/<role>.json` (D7). |
| F10 | Credentials are never logged | `execute_setup_steps` logs every step dict (`playwright_scanner.py:309`: `{action} → {step[action]!r}`), so a `fill` with a literal `value:` is printed in full. The buggy_shop template uses literal values for its seeded users. | Redact `value` in that log line (strengthening; D7). |
| F11 | Specs pick a role | Benchmark modules log in through `modules[].setup`, which ScriptGeneration renders into `test.beforeEach` with literal values (`script_generation/agent.py:1456-1480`). | `test.use({ role })` from the renderer is a 4.5 change; this session ships the runtime side (D7). |
| F12 | Suites are tag-based | `resolve_suite_spec_files` (`suite_orchestrator.py:21`) turns spec ids into file paths, plus an optional per-entry `grep`. UIExecution runs **one Playwright process per grep entry** (`agent.py:299-309`). The 4-level CLI's level 3 globs `test_scripts/individual/test_<id>_*.spec.ts` (`suite_orchestrator.py:226-238`), a legacy layout, so modern projects get `no_tests`. | Suite → grep translation (D9). |
| F13 | Grep needs tags on every test | Playwright 1.64 matches `--grep` against **project name + spec file path (relative to testDir) + describe titles + test title + tags** (`lib/common/index.js:2845-2855`, `_grepTitleWithTags`). Every rendered spec has the spec id in its file name (`test_M03_BS_003_….spec.ts`) and in its describe title (`"… (M03_BS_003)"`). | A spec id can be grepped without any new tag, so specs generated before Phase 1 work too (D9). |
| F14 | — | UIExecution's list-reporter regex accepts `\[[\w\-]+\]` as project name (`agent.py:91-99`). `devices['Pixel 7']` contains a space. | Project names are slugs: `pixel-7`, `iphone-14` (D4). |
| F15 | — | The blob reporter **removes its output folder** at start (`lib/runner/index.js:3146`) and names files `report-<shard>.zip`. | Each shard writes its own folder; the zips are collected before the merge (D8). |
| F16 | — | No unit test pins the Playwright command line (`grep project=chromium tests/unit` → none). | The command shape can change without breaking tests. |
| F17 | Benchmark project exists | `bench_*` projects are gitignored and absent from this worktree. The Phase 3 quick suite (6 specs / 61 tests, M03 + M04) is in the main checkout under `application_assets/projects/bench_buggy_shop/`. | §7: copy it in (read-only source) for the before/after run. |
| F18 | — | `pytest` and `hypothesis` are not installed in this worktree's `.venv`; `hypothesis` (used by Phase 3 tests) is missing from `requirements-dev.txt`. | Installed locally. I propose adding `hypothesis` to `requirements-dev.txt` (one line). |
| F19 | — | The Python `playwright` package (scanner, discovery, auth) is 1.63.0 (`requirements.txt: playwright>=1.40.0`). | Unchanged. The Node and Python packages install their own browser builds. |

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| **D1** | Pin `"@playwright/test": "1.64.0"` (no `^`), refresh `package-lock.json`, `npx playwright install chromium` (1.64 needs its own browser build). Record the version in `docs/audit/current_state.md` §5. | Latest stable (F1/F2). If you want a release that has been out for ≥ 2 weeks, use `1.63.0` instead; every feature in F2 also exists in 1.63. |
| **D2** | **Config builder.** New pure function `buildPlaywrightConfig({ env, projectYaml })` in `runtime/config/buildConfig.ts`; `playwright.config.ts` becomes a thin wrapper. project.yaml is parsed with the npm package **`yaml@2.9.1`** (pinned, zero dependencies, ISC), a new devDependency. `baseUrl.ts` and its line scanner stay as they are. | The matrix, roles and locale need real YAML; extending the hand-written line scanner would be fragile. Keeping `baseUrl.ts` keeps Phase 0 behaviour byte-identical. |
| **D3** | **New top-level `execution:` block** in project.yaml (separate from the existing `test_execution.suite`; see §3 for keys and defaults). It is resolved twice: by Pydantic in Python (`tools/execution/config.py`, added to the request by `project_manifest`) and by the TS builder. One shared case file, `tests/fixtures/execution_config_cases.json`, is asserted by **both** pytest and vitest, so the two sides cannot drift. `test_id_attribute` is also applied to Python live validation and the healing check (`playwright.selectors.set_test_id_attribute`). | Python needs the projects (D4), shards, suite mode and role auth before Playwright starts; TS needs them for hand runs (`PW_PROJECT=x npx playwright test`). Aligning Python with TS fixes F8. Validation still requires `count() == 1`; it now checks the same attribute the runtime uses. |
| **D4** | **Projects.** `chromium` always; the matrix can add `firefox`, `webkit`, `pixel-7` (`devices['Pixel 7']`) and `iphone-14` (`devices['iPhone 14']`). `test_generation.profile: smoke` forces chromium only, with a warning if the matrix lists more. Unknown names: warning and ignored. UIExecution passes one `--project=<name>` per resolved project (no more hard-coded `chromium`). A missing browser binary is reported with the browser's name and the `npx playwright install <browser>` command. | F6, F14. With no `execution:` block, `--project=chromium` is all that is passed, exactly as today. |
| **D5** | **Config values:** `trace: 'retain-on-failure'`, `video: 'retain-on-failure'`, `screenshot: 'only-on-failure'` (each can be overridden in `execution:`). `forbidOnly: !!CI` stays. `testIdAttribute`, `locale` and `timezoneId` come from `execution:`; locale and timezone stay unset by default. **`retries` stays 0, `fullyParallel` stays off**: retries come with 4.7 (until then `_parse_playwright_json` counts a fail-then-pass as passed, `agent.py:899`), and `fullyParallel` comes with 4.4's data isolation. **Output layout per run `{ts}`:** `json/{ts}_results.json` and `html/{ts}/` (unchanged), `test-results/{ts}/` (new `--output`, fixes F7), `junit/{ts}.xml`, `mta/{ts}.mta_results.json`, and `blob/{run_id}/` (sharded runs only). | Evidence survives; reporters stay additive. |
| **D6** | **MTA reporter** `runtime/reporters/mta-reporter.ts` → `mta/{ts}.mta_results.json`. Per test: `test_id` (Playwright id), `title`, `title_path`, `spec_file`, `line`, `project`, `tags`, `annotations`, `tc_id`, `case_id`, `scenario_id`, `ac_ids`, `status` ∈ `passed / failed / flaky / skipped / timedOut / interrupted` (from `outcome()` and the last result), `retries`, `duration_ms`, `attempts[]` (status, duration, error message, ANSI stripped, ≤ 2,000 chars), `attachments[]` (name, content type, path; never the bodies). Run level: `run_id`, `shard`, totals, timestamps. Written atomically. Contract: `MtaResultsV2` in `contracts/artifacts/models.py` + `schemas/mta_results.v2.schema.json`. A Python loader, `tools/execution/mta_results.py`, turns it into UIExecution's result shape. A contract test proves `tools.requirements.traceability.apply_results` accepts that output. This session, UIExecution keeps folding the Playwright JSON into traceability (unchanged) and records the `mta_results` path in its result and in `execution_results`. The MTA file becomes the source of truth with 4.7. | User spec: a results file that traceability can consume. Changing which file traceability reads, together with the flaky status, is a single 4.7 change. |
| **D7** | **Auth per role = Python pre-step + `role` fixture**, not a TS setup project. `tools/auth/role_states.py::ensure_role_states()` reuses `deep/roles.open_role` in headless Chromium and writes `application_assets/projects/<p>/.auth/<role>.json`. That path is already gitignored (`.gitignore:126`). A file younger than `execution.role_auth_max_age_minutes` is reused. `storageState` roles use their own file (existence checked); `anonymous` has no file. UIExecution runs the pre-step when `execution.role_auth: true`. `python main.py --project X --auth-setup` additionally captures the roles when `auth.roles` exists; its single-identity behaviour is unchanged. Standalone CLI: `python -m tools.auth.role_states --project X [--role R] [--force]`. A role that fails to log in is listed in the run result (`role_auth.failed[]`) and the run continues; a spec that uses that role fails in its fixture with the reason. **TS:** `role` option fixture (`test.use({ role: 'admin' })`) plus an override of the built-in `storageState` option: `storageState` role → its path; `anonymous` → `{cookies: [], origins: []}`; any other role → `.auth/<role>.json`. A missing file or an unknown role throws, naming the CLI to run. With no `role`, the config's `PW_STORAGE_STATE` applies as today. **Secrets:** only role names and paths are logged; F10's log line is redacted. Credentials come from env vars (`credentials`, `value_env`); a literal `value:` is the project author's choice and is no longer printed. | A setup project is a test, so its `fill(password)` would be recorded in `trace.zip` and in the HTML/JSON step lists. A Python pre-step keeps credentials out of every Playwright artifact by construction, and reuses the login code Phase 2 already tests. |
| **D8** | **Shards + merge.** Request / CLI: `shard: "i/n"` (`--shard i/n`) runs one shard (CI style): blob into `blob/<run_id>/shard-<i>/`, no merge. `shards: n` (`--shards n`) runs every shard, sequentially or up to `execution.max_parallel_shards` at once, then merges. `merge_run: <run_id>` (`--merge-reports <run_id>`, or `python -m tools.execution.merge_reports --project X --run <id>`) merges an existing blob folder (CI merge job). The blob reporter is added **only** when `PW_BLOB_DIR` is set. The merge runs `npx playwright merge-reports --config playwright.merge.config.ts <dir>`; that config holds only reporters (json, html, junit, MTA) and never resolves a base URL (F4). Shard zips are copied into one folder first (F15). The merge writes the normal `json`/`html`/`junit`/`mta` files, adds one report-index entry, and is parsed like any run. Sharding applies inside each Playwright invocation, so the per-module split (Phase 0.6) shards each module run and `_merge_runs` combines them as today. Headed mode and healing's `spec_files` re-runs never shard. | Plan 4.8; same totals as an unsharded run (acceptance criterion 6). |
| **D9** | **Suites by tag.** UIExecution and `main.py` accept `grep` / `--grep "@smoke\|@P0"` and `grep_invert`. **`test_suites/*.json` → one grep expression** (`tools/execution/suite_grep.py`): spec ids, including `SC-M01-003` ordinals resolved through `test_suite.json`, become `(?<![A-Za-z0-9])(M01_BS_001\|M02_BS_001)(?![0-9])`; this matches the file name and describe title of old and new specs (F13). A per-entry `grep` is combined with its id as `(?=.*ID)(?=.*GREP)`. New optional suite keys `tags: ["@smoke", "@P0"]` and `grep` (ORed in). `all_modules: true` → no grep. Unresolved ids are reported, as today. One Playwright process instead of one per grep entry. Behind `execution.suite_mode: files \| grep`; **default `files`** (today's path targeting, unchanged), `grep` in the project template and the benchmark. 4-level CLI: level 3 also applies the translation when the suite has `tags`/`grep`, or when the legacy `individual/` folder doesn't exist (today that case returns `no_tests`); levels 1, 2 and 4 are unchanged. | Plan 4.9 with no new tags required. A tag-only scenario tag (`@M01_BS_001`) would need a renderer change (4.5) and would not cover existing specs. |

## 3. project.yaml flags and defaults

```yaml
execution:                          # Phase 4 — every key optional; defaults shown
  matrix: [chromium]                # + firefox | webkit | pixel-7 | iphone-14   (profile smoke → chromium only)
  test_id_attribute: data-testid    # Playwright's default; sauceLabs is migrated to data-test (§6)
  locale: null                      # e.g. en-GB      → use.locale
  timezone_id: null                 # e.g. Europe/London → use.timezoneId
  trace: retain-on-failure
  video: retain-on-failure
  screenshot: only-on-failure
  junit: true                       # reports/junit/{ts}.xml
  mta_reporter: true                # reports/mta/{ts}.mta_results.json
  role_auth: false                  # true → log in every auth.roles role before each run (.auth/<role>.json)
  role_auth_max_age_minutes: 30
  suite_mode: files                 # files = legacy path targeting | grep = test_suites/*.json → --grep
  shards: 1                         # > 1 → run N shards locally + merge-reports
  max_parallel_shards: 1
```

With no `execution:` block, a project behaves exactly as today except for (a) trace/video `retain-on-failure` instead of
`on-first-retry` (which never recorded), (b) the new JUnit and MTA files, (c) `data-testid` instead of `data-test`
(migrated where it matters, §6), and (d) `--output` moving to `test-results/{ts}/` (bug fix F7). The project template
and the buggy_shop template set `role_auth: true` and `suite_mode: grep`.

## 4. Files

**New**
- `application_assets/_shared/runtime/config/buildConfig.ts` (+ `buildConfig.test.ts`): project.yaml/env → config, projects, reporters, roles.
- `application_assets/_shared/runtime/reporters/mta-reporter.ts` (+ `mta-reporter.test.ts`).
- `application_assets/_shared/runtime/auth/roles.ts` (+ `roles.test.ts`): role → storageState resolution, used by the fixture.
- `playwright.merge.config.ts`: reporters only.
- `tools/execution/__init__.py`, `config.py` (the `execution:` block), `mta_results.py` (loader), `suite_grep.py` (suite → grep), `merge_reports.py` (blob collect + merge + CLI), `shards.py` (shard planning, per-shard env).
- `tools/auth/role_states.py` (pre-step + CLI).
- `schemas/mta_results.v2.schema.json` (generated).
- `tests/fixtures/execution_config_cases.json` (shared pytest/vitest cases).
- Tests: `tests/unit/test_execution_config.py`, `test_mta_results_loader.py`, `test_suite_grep.py`, `test_ui_execution_shard_merge.py`, `test_ui_execution_projects_and_outputs.py`, `test_role_states.py`, `test_setup_steps_redaction.py`, `test_suite_orchestrator_grep.py`; e2e `tests/integration/test_phase4_runtime_e2e.py` + specs in `tests/e2e/phase4/` (buggy_shop, real browser; proves criteria 4–6).

**Changed**
- `package.json`, `package-lock.json`: pin `@playwright/test` 1.64.0; add `yaml` 2.9.1.
- `playwright.config.ts`: calls the builder.
- `runtime/fixtures/testFixture.ts`: adds the `role` option and the `storageState` override (`action` unchanged).
- `agents/test_execution/ui_execution/agent.py`: projects, `--output` fix, report env vars, role pre-step, shards/merge, grep and suite mode, browser-missing message; `agent.md` / `agent.json` (version 1.3.0, new inputs/outputs).
- `tools/suite_orchestrator.py`: grep translation for level 3 (additive).
- `tools/project_manifest.py`: `flat["execution"]`.
- `tools/playwright_scanner.py`: redact `value` in the setup-step log line (one line).
- `tools/test_creation/script_generator/locator_resolve.py`, `agents/test_execution/healing/tools.py` (the `_live_locator_resolves` launch only), and ScriptGeneration's validation launch: apply `test_id_attribute`.
- `tools/auth/auth_setup.py` and `main.py`: `--auth-setup` also captures roles; new flags `--grep`, `--shard`, `--shards`, `--merge-reports` (additive).
- `contracts/artifacts/{models,registry,paths}.py`: `mta_results` contract (additive).
- Templates: `aAprojectTemplate/project.yaml` and `buggy_shop/mta_project/project.yaml.tmpl` get the `execution:` block (commented examples in the template). `sauceLabs/project.yaml` gets `execution.test_id_attribute: data-test`.
- Docs: README ("Execution", "Playwright configuration", "Auth Setup", "Modular Execution", Quick Start), `docs/audit/current_state.md` (version), `requirements-dev.txt` (+ `hypothesis`, F18).

**Not touched:** `frontend/**`, `api/**`, `workflows/**` (no new agent or step), `agents/registry_setup.py`, `tools/agent_eval/**`, `tools/agent_tests/**`, `eval_sets/**`, `benchmarks/agents/**`, the renderer (4.5), ActionEngine (4.6).

## 5. Tests

| Kind | Coverage |
|---|---|
| vitest | config builder: matrix/profile → projects, unknown names, testId/locale/timezone, reporters with and without blob/junit/mta, merge config has no baseURL, shared cases file; MTA reporter: output shape, status mapping (passed/failed/flaky/skipped/timedOut/interrupted), annotations → tc/ac/case/scenario, attachments without bodies, atomic write; roles: storageState/anonymous/generated paths, unknown role, missing file message. |
| pytest | `execution:` resolution + shared cases file; suite JSON → grep (ids, ordinals, per-entry grep, tags, `all_modules`, unresolved ids, regex anchoring: `M01_BS_001` must not match `M01_BS_0010`); UIExecution: `--project` list, `--output` ≠ HTML folder, report env vars, shard command lines, blob collection, merge invocation, merged parse + single index entry, headed/healing never shard; MTA loader → `apply_results` contract; role pre-step (fake browser): reuse by age, failure listed, nothing secret logged; setup-step log redaction; 4-level CLI grep path. |
| e2e (Chromium, buggy_shop) | 2 roles + anonymous; JUnit + MTA output linked to TC/AC; 2 shards + merge totals = unsharded totals. |

## 6. Migration plan

1. **Existing generated specs:** no re-render in this session (the renderer is unchanged). They import the same `testFixture`, so `role` is just an extra option. Their `test.use({ baseURL })` and `beforeEach` logins keep working.
2. **Test-id attribute:** `sauceLabs/project.yaml` gets `execution.test_id_attribute: data-test`. AWS_Test, AWS_World and Blog_Writing_Agent use `data-testid` (aws.amazon.com and Streamlit). Their testid keys already passed Python validation; with the new default they will also resolve at run time (F8). Projects without testid entries are unaffected. Archived projects under `application_assets/myTestProjects/` are not executable by `PW_PROJECT` and are left alone.
3. **Report folders:** new subfolders only. Healing still reads `reports/json/` (unchanged).
4. **`test_suites/*.json`:** unchanged files, unchanged behaviour under the default `suite_mode: files`.
5. **Single-identity auth** (`auth.enabled` + `storage_state_path` / `live_login`): unchanged path through `PW_STORAGE_STATE`.

## 7. Benchmark plan (before / after)

The Phase 3 quick suite (M03 + M04, 61 tests) is copied from the main checkout into this worktree's gitignored
`application_assets/projects/bench_buggy_shop/`. That only reads from the other checkout. Then:
`python -m tools.benchmark.run --app buggy_shop --skip-generate --no-healing --label phase4_before` on unchanged code
first, and `--label phase4_after` at the end (no LLM spend). Regression check: per-test pass/fail identical on the
bug-free build; same bugs caught. Runtime delta reported (retain-on-failure video/trace costs time).

## 8. Mismatches with the plan / the request, and proposed adjustments

| Plan / request | Adjustment | Reason |
|---|---|---|
| 4.3 "setup project (or globalSetup)" | Python pre-step reusing Phase 2's `open_role` + a TS `role` fixture | Credentials would otherwise be recorded in traces and reports (D7). Hand runs: `python -m tools.auth.role_states` first, the same pattern as today's `--auth-setup`. |
| 4.2 `fullyParallel: true` | Stays false this session | Only with 4.4 data isolation (as the request says); 4.4 adds the flag. |
| 4.2 MTA reporter "writes results straight into `traceability.json`" (plan) | Separate `mta_results.json` + Python loader + contract test | The request's wording; traceability stays owned by Python (Phase 1). |
| 4.9 "spec ids → tags" | Spec ids → grep on file name / describe title | Works for every existing spec without re-rendering (F13). A scenario tag can be added with 4.5. |
| `testIdAttribute` default `data-testid` | Also applied to Python validation and healing | Otherwise Python and TS disagree (F8). |
| (not in plan) | Fix `--output` / HTML folder clash | Without it, retain-on-failure evidence is deleted (F7). |
| (not in plan) | Redact literal setup values in logs | Required by "credentials never written to logs" (F10). |
| retries / `failOnFlakyTests` | Untouched (verified available) | 4.7, next session. |

## 9. Risks

- **R1 Runtime:** `retain-on-failure` records video and trace for every test (deleted on pass). Expect a slower run; it is measured in §7 and can be turned off per project (`execution.video: off`).
- **R2 Two resolvers** (Python + TS) for `execution:`: mitigated by the shared case file tested on both sides.
- **R3 Browser builds:** 1.64 needs `npx playwright install chromium` again; firefox/webkit only when the matrix asks, with a fail-fast message.
- **R4 Session tokens in evidence:** retained traces contain cookies of the role's session (not credentials). They stay under the gitignored `reports/` tree; documented.
- **R5 Grep over the whole scripts folder** compiles every spec in the project folder; a spec with a syntax error breaks a grep run where file targeting would have skipped it. Mitigation: `suite_mode` defaults to `files`; the run reports the compile error.
- **R6 Shards:** a shard with zero tests (n > tests) exits without results; the merge treats a missing shard zip as empty, not as a failure.
- **R7 1.64.0 is 5 days old** (D1 alternative: 1.63.0).

## 10. Decisions I need from you

1. **Version:** `1.64.0` (recommended, latest stable) or `1.63.0` (≥ 1 month old)?
2. **D7:** Python pre-step for role auth instead of a Playwright setup project. OK?
3. **D9 default:** `suite_mode: files` for existing projects and `grep` in the templates. OK, or should `grep` be the global default?
4. **D2:** adding the `yaml` npm devDependency. OK?
5. **§7:** copy the Phase 3 benchmark project from the main checkout (read-only) for before/after. OK?
