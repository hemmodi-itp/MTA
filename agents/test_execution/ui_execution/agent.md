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
