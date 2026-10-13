# Phase 11-lean report — Report + Final Results
Flags: `reporting.enhanced` and `quality_gates` in project.yaml (absent = OFF; ON in the buggy_shop `project.yaml.tmpl`).

**Changed**
- New `tools/reporting/summary.py`: summary metrics (AC coverage, pass rate P0–P3, triage product defects, failed @a11y/@security counts, weak_oracle, AI-agent dimension outcomes), traceability CSV, not-tested list, defect list (plan steps, expected from verify steps, actual from first error, screenshot/trace attachments), gates `p0_pass_rate` and `requirement_coverage`. CLI `python -m tools.reporting.summary <report.json>` exits 1 when a gate fails.
- ReportingAgent: builds `report["quality"]` and writes `reports/csv/<ts>_<project>.traceability.csv`; returns `quality_gates`. Non-fatal on error.
- html_report: Executive Summary, "Not tested & why" and Defects sections at the top; the existing traceability table links the CSV.

**Tests**: `tests/unit/test_reporting_quality.py` 3/3 (metrics, CSV, gate exit code); 207 existing report/html/traceability tests pass.

**Benchmark**: buggy_shop (reused suite, `--skip-generate`): AC coverage 25.9%, detection 3/22, false-failure 18.0%, flaky 1.6%. buggy_bot mock: 14/14 detected, 0 false positives. Details are in `docs/phases/final-results.md`.

**Caveats**: the benchmark runner calls UIExecutionAgent directly, so ReportingAgent's new sections were exercised by unit tests only, not by this run. Playwright needed the `yaml` npm package, installed with `--no-save` (backlog item).

**Deferred**: see docs/backlog.md "Phase 11".
