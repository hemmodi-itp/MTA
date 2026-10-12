# UIExecutionAgent

Runs the generated TypeScript Playwright `.spec.ts` files (or, as a legacy fallback, pytest `.py`
files) and returns pass/fail results.

## Mode selection

- **TypeScript mode** — any `.spec.ts` found in `test_scripts/` → `npx playwright test`
- **Python mode** — only `.py` files present → `pytest` (backward compat, no LOC-ID resolution)

## Inputs
- `test_creation/test_scripts/*.spec.ts` (or `*.py` in pytest-compat mode)
- `test_creation/test_suite.json`
- `playwright.config.ts`
- `module_filter` (optional — scope to one module's specs)
- `suite` (optional — named suite execution)

## Outputs

```json
{
  "module": "ui_execution",
  "status": "success|failed|skipped",
  "suite": "<project>",
  "mode": "playwright|pytest",
  "passed": N, "failed": N, "skipped": N,
  "scenarios_executed": N,
  "returncode": N,
  "results": [
    {
      "spec_file": "...", "test_title": "...", "test_case_id": "BS-NNN",
      "business_scenario_id": "BS-NNN", "status": "success|failed",
      "duration_ms": N, "errors": [...], "comment": "", "no_interaction_close": false
    }
  ],
  "report_json": "<path>"
}
```

Results are a **flat list** — no nested `result.steps[]` — with `test_case_id`/`business_scenario_id`
derived from `spec_file` via the `BS-\d+` pattern.

## Notable behaviors

- Streams stdout in real time; handles `KeyboardInterrupt` gracefully (summarizes completed tests,
  marks unstarted ones `skipped`).
- Browser-close errors are marked `skipped`, not `failed`; 3+ consecutive no-interaction browser
  closes switch remaining specs to headless.
- No Chromium/Playwright auto-install during execution (deliberate — locked-down client servers
  often have no outbound network access mid-run); fails fast instead with an actionable error.
- `live_login` auth strategy captures a fresh storage state before each run.
- Recursive spec discovery (`os.walk`) — finds specs nested under per-module subdirectories.

## Failure mode

No tiered fallback — infrastructure failures (missing scripts dir, Playwright not installed, process
launch failure) return `status: failed` directly.

## Base URL resolution (Phase 0.6) — fail fast, no default

`_run_playwright` resolves the target with `tools/base_url.py`: `request["url"]` →
`project.url` → the URL of the targeted module(s) → the single distinct module URL. If
nothing resolves it returns `status: failed, blocking: True` without starting Playwright
(the old silent `localhost:3000` fallback is gone). A run whose specs span modules with
**different** URLs is split into one Playwright run per module, each with its own
`BASE_URL`, and the results are merged (`_merge_runs`; a failed sub-run's error is kept in
`run_errors`).

## Safety rails (Phase 0.5)

`MTA_ALLOWED_HOSTS` is always set from the project's `SafetyPolicy` (`safety.allowed_hosts`,
or the hosts of the project's own URLs). The shared runtime (`ActionEngine.navigate` and the
fixture's main-frame `framenavigated` guard, `application_assets/_shared/runtime/safety.ts`)
fails the step when the page goes to a host outside that list. A base URL whose host is not
allowed is logged as a warning.

## Normalised run record (Phase 0.7)

Every completed run also writes `test_execution/reports/mta/{ts}.execution_results.json`
(contract `execution_results` v2: counts, base URL, per-test results). It lives outside
`reports/json/`, which HealingAgent scans for the latest Playwright report.

## Traceability fields (Phase 1)

Each per-test result (and the `execution_results` v2 record) gains, additively:

| Field | From |
|---|---|
| `pw_status` | Playwright's raw test status (`expected`, `unexpected`, `skipped`, `flaky`, …) |
| `tags` | the spec's tags (`P1`, `AC-01.2`, …) |
| `annotations` | `[{type, description}]` — `ac`, `tc`, `scenario`, `ac_link` |
| `tc_id`, `ac_ids` | from the `tc` / `ac` annotations, when present |

`status` itself is unchanged — Playwright `skipped` still maps to `failed` there (design D6; revisit with P4.7);
traceability uses `pw_status`, so a skipped test is recorded as skipped. After every Playwright run (including
HealingAgent's `run_tests` re-runs and per-module split runs) the results are folded into
`test_creation/traceability.json` when `requirements.enabled` is on; a traceability failure is logged and never
fails the run.

## Playwright runtime (Phase 4)

Configuration comes from the project's `execution:` block (`tools/execution/config.py`; the TS config builder
resolves the same block) plus these request overrides:

| Request key | Effect |
|---|---|
| `browsers` | Run these projects instead of the matrix: `chromium`, `firefox`, `webkit`, `pixel-7`, `iphone-14` |
| `grep` / `grep_invert` | `--grep` / `--grep-invert`. ANDed with a suite's grep |
| `shards` | Run N local shards (`--shard=i/N`, list + blob reporters only, `execution.max_parallel_shards` at a time), then `merge-reports` into the normal outputs |
| `shard` + `run_id` | One CI shard: normal reports plus a blob in `reports/blob/<run_id>/shard-<i>/` |
| `merge_run` | Merge `reports/blob/<run_id>/` (CI merge job). Playwright test is not run |

Behaviour:
- **Projects.** One `--project=` per enabled project (the matrix; `chromium` only by default). `MTA_PROJECTS` tells
  the config builder which projects to define.
- **Output folder.** `--output` is `reports/test-results/<ts>/`, no longer the HTML report folder, which the HTML
  reporter empties.
- **Report files.** `PW_JUNIT_REPORT` → `reports/junit/<ts>.xml`; `MTA_RESULTS_FILE` →
  `reports/mta/<ts>.mta_results.json`. The MTA reporter writes per-test TC/AC ids, a status that keeps `flaky`
  apart, attempts and attachment paths. Both paths are returned as `report_junit` / `mta_results` and recorded in
  `execution_results`. A per-module split also returns `*_all` lists.
- **Suites.** `execution.suite_mode: grep` turns a `suite` into one `--grep` run over its module folders
  (`tools/execution/suite_grep.py`). The default `files` mode keeps per-file targeting.
- **Role auth.** With `execution.role_auth: true`, every `auth.roles` role is logged in once per `execute()`, before
  Playwright starts (`tools/auth/role_states.py`), so `test.use({ role })` finds `.auth/<role>.json`. The summary is
  returned as `role_auth`; a failed role never fails the run.
- **Never sharded:** headed runs and `spec_files` re-runs (healing).
- **Error messages.** A missing browser binary names the browser to install. A grep that matches nothing returns
  `status: skipped`.
- **Unchanged until Phase 4.7:** `retries: 0`, and the flaky→pass counting in `status`.
