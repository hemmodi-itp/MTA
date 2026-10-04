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
