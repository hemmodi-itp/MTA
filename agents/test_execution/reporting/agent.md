# ReportingAgent

Aggregates Playwright JSON results + `test_suite.json` into HTML and JSON execution reports.
Pure Python — no LLM calls.

## Inputs
- Playwright JSON results file
- `test_creation/test_suite.json`
- Workflow state (project name, run ID)

## Outputs
- `test_execution/reports/html/{timestamp}_{project}.html` — internal HTML summary
- `test_execution/reports/json/{timestamp}_{project}.json` — internal JSON report
- `test_execution/reports/index.json` — updated index

## Result-shape handling

Reads execution results from whichever step actually ran — `outputs["execution"]` (legacy
`ExecutionAgent`, nests summary fields under a `"summary"` key) or `outputs["ui_execution"]`
(current default, `UIExecutionAgent`'s flat top-level fields) — falling back to whichever is present.
Per-test rows read `test_case_id`/`business_scenario_id`/`status`/`errors` directly from the flat
result shape.

## Degraded spec handling

Specs with `fallback_route != null` in `test_suite.json` are rendered with a **warning badge** in the
HTML report so QA can prioritise manual review.

## Healing section

Reads `specs_healed`/`tests_healed` from the healing step's output (matching `HealingAgent`'s actual
field names — these do not map to the older `locators_healed`/`unresolved` concept from a prior
architecture).

## Fallback behaviour
- **FALLBACK** → `fallback_core.fallback_report()` — minimal `report_fallback.json` with pass/fail counts and list of failing test names (no HTML).

## Requirements traceability section (Phase 1)

When `requirements.enabled` is on and `requirements.json` exists, ReportingAgent (always runs, after healing)
rebuilds `test_creation/traceability.json` and adds `report["traceability"]`
(`tools.requirements.traceability.report_section`): the summary (AC coverage of automatable criteria, ACs
passing / failing, reasons), every AC with its tests and latest result, **every AC with zero tests and why**
(`not_testable`, `manual_only`, `not_supported:api`, `not_supported:non_functional`, `no_url`,
`module_not_generated`, `no_scenario`, `dropped_for_safety`, `missing_locator`, `missing_action`,
`placeholder_negative_dropped`, `locator_type_mismatch`, `budget`, `generation_failed`, `no_test_targets_ac`),
and the tests linked to no AC. The HTML report renders it as "Requirements Traceability". A failure here is
logged; reporting continues.

## Quality section (Phase 11, `reporting.enhanced` / `quality_gates`)

`report["quality"]` and the top of the HTML report (`tools/reporting/summary.py`, `tools/reporting/insights.py`):

- **Executive summary** — gate verdict, AC coverage, pass rate by priority, product defects by severity (P0→critical …
  P3→low; @a11y/@security → high), critical a11y / high security findings (read from the `a11y-findings.json` /
  `security-findings.json` the NFR specs attach), worst performance regression, flaky rate. Every number links to the
  section that lists its evidence.
- **Top 5 risk areas** (failures by priority, untested P0/P1 criteria, flaky) and **trend vs the last 5 runs**
  (`reports/history.json`, one row per run, last 50 kept).
- **Defects** with steps, expected (and where the expected value came from), actual, severity, and evidence:
  screenshot, trace, video, HAR (plus the failed requests), console log, browser, role, environment, run id.
  Exports for trackers: `reports/defects/<ts>_<project>.jira.json` (Jira REST create-issue payloads; key from
  `reporting.jira_project`) and `.ado.json` (Azure DevOps JSON-Patch). Nothing is posted to a tracker.
- **Traceability matrix**: filterable, sortable HTML table, CSV and XLSX (`reports/csv/`).
- **Coverage dashboard**: requirement, technique, element, page/state, transition, API endpoint, role matrix,
  browser, test type; code coverage is reported as not measured.
- **Test Summary Report** (ISO/IEC/IEEE 29119-3: scope, approach, deviations, coverage, results, defects, residual risk,
  recommendation) in the HTML and as `reports/summary/<ts>_<project>.test_summary_report.md`.
- **Quality gates**: `p0_pass_rate`, `p1_pass_rate`, `requirement_coverage` (minimums) and `max_critical_a11y`,
  `max_security_high`, `max_flaky_rate`, `perf_budget_regression_pct` (maximums). `python main.py` exits 1 when a gate
  fails and prints the gate (`--ignore-gates` to exit 0); `python -m tools.reporting.summary <report.json>` does the
  same for a saved report.

## Quarantine (Phase 10.2)

`<project>/quarantine.yaml` (`tools/execution/quarantine.py`) lists tests that still run but do not gate. On every
run (whether or not `reporting.enhanced` / `quality_gates` is set) the results are split first: gates, pass rates and
the executive summary use the gating tests only; the quarantined ones are listed in `report["quarantine"]` (test and
this run's status; released / added / reset this run) and in the HTML "Quarantine" section. After each run
`record_run` updates the file: a quarantined test that passes `release_after` (default 5) runs in a row is released
(kept in `released:` history), a failure resets its count, and a test flaky again after an earlier flaky run (last 10
JSON reports) is quarantined automatically with reason `flaky`. `summary["quarantined_tests"]` counts them.
