# Phase 11 report — Reporting and Quality Gates (complete)

Builds on Phase 11-lean (`6b4cfcc`). Flags unchanged: `reporting.enhanced`, `quality_gates` (absent = off).

**11.1 Executive summary**: gate verdict, AC coverage, pass rate by priority, **defects by severity** (P0→critical …
P3→low; @a11y/@security → high), critical a11y / high security findings **read from the findings JSON the NFR specs
attach** (no longer "failed @a11y tests"), worst performance regression, flaky rate, **top 5 risk areas** (failures by
priority, untested P0/P1 criteria, flaky) and **trend vs the last 5 runs** (`reports/history.json`). Every number links
to the section with its evidence (`#defects`, `#not-tested`, `#traceability`, …).

**11.2 Traceability matrix**: the HTML table is filterable and sortable (inline JS, works offline); exports CSV and
**XLSX** (header filter, frozen header, result colours) under `reports/csv/`.

**11.3 Coverage dashboard**: requirement, technique (selected/designed), element (locator keys used by specs), page/state,
transition, API endpoint, role matrix, browser/device, test type; code coverage reported as "not measured".

**11.4 Defects**: severity, plan steps, expected **and where the expected value came from**, actual, and evidence —
screenshot, trace, video, HAR (with the failed requests listed), console log, browser, role, environment, run id.
UIExecutionAgent rows now carry `browser` and the last attempt's `attachments` (they had none before, so defect
evidence links were always empty). Exports: `reports/defects/<ts>_<project>.jira.json` (Jira REST create-issue
payloads) and `.ado.json` (Azure DevOps JSON-Patch); nothing is posted.

**11.5 Gates**: added `p1_pass_rate`, `max_critical_a11y`, `max_security_high`, `max_flaky_rate`,
`perf_budget_regression_pct`. **`python main.py` now exits 1 when a gate fails** and prints the gate
(`--ignore-gates` to exit 0).

**11.6 Test Summary Report** (ISO/IEC/IEEE 29119-3: scope, approach, deviations, coverage, results, defects, residual
risk, recommendation) in the HTML and as `reports/summary/<ts>_<project>.test_summary_report.md`.

**Bugs fixed in the lean pass's code** (found by the new end-to-end test):
- ReportingAgent's quality section read the display rows of `test_execution_report` (no spec, tc_id, tags, status
  detail, attachments) — pass rate by priority, defects and gates came out empty on real runs. It now reads the
  execution step's own results.
- Defects never matched their triage verdict: triage spec keys were passed through the spec-key function again and
  reduced to a basename. Matching is by spec key now.
- A defect's steps were found only by tc_id; untraced projects now match the plan test by its rendered title.

**Tests**
- `tests/unit/test_phase11_reporting.py` — 22: severity, risk areas, history/trend, coverage dashboard, NFR counts,
  10 gate cases + config, evidence, Jira/ADO, defects, 29119-3, XLSX, HTML anchors + interactive matrix, exit code.
- `tests/integration/test_phase11_report_e2e.py` — real buggy_shop run with BUG_18 → TriageAgent → ReportingAgent:
  1 product defect with an existing screenshot, gates FAIL and `main.gate_exit` returns 1, Jira/XLSX/29119-3 files
  written, report sections present, no external URL in the HTML (renders offline). Passes.

**Open**: docs/backlog.md → Phase 11 (tracker posting, code coverage, traffic-based API coverage).
