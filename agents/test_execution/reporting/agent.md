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
