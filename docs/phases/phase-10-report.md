# Phase 10 report — Execution at Scale: Flakiness, CI, Selective Runs

New package `tools/execution/` (`quarantine.py`, `health.py`, `admission.py`, `selective.py`) and the CI entry point
`tools/ci/run.py`, with templates `ci/github-actions.yml` and `ci/azure-pipelines.yml`. Wired into UIExecutionAgent
(health check, `workers` override), ReportingAgent (quarantine), the orchestrator (`environment_blocked` stops the
steps after it) and `main.py` (exit 3).

**10.1 Burn-in admission** (`admission.admit`): specs with status `new` or `healed` in `test_suite.json` run
`--repeat-each=5` before they join the regression suite. Per test: 5/5 passes → admitted; some passes → quarantined
(`burn_in_failed`); 0/5 → not admitted, left for triage (it fails every time, so it is a defect or a broken test, not
flakiness). At most 50 specs per run, oldest first; the rest wait for the next nightly. The spec records the outcome in
its `admission` field.

**10.2 Flaky-test quarantine** (`quarantine.py`): `<project>/quarantine.yaml` holds test, first seen, reason
(`flaky` / `burn_in_failed` / `order_dependent` / `manual`), failure signature and owner. Quarantined tests still run and
are reported, but do not count for quality gates, pass rates or the CI exit code. After every run a test's stable passes
are counted: 5 in a row release it (kept in `released:` history), a failure resets the count. A test that is flaky
again after an earlier flaky run (last 10 reports) is quarantined automatically. The HTML report has a "Quarantine"
section and the executive summary shows the count.

**10.3 Order independence** (`admission.order_check`, nightly with `--order-check`): the same specs run three ways:
the normal run, one spec file per run in reverse file order, and 4 workers. A test that passes one way and fails
another is marked `order_dependent` and quarantined with that reason.

**10.4 Pre-run health check** (`health.py`, project.yaml `health_check:`): checks that the base URL answers (< 500), that
each role's saved session still opens `auth_url` without a redirect to the login (an expired one is refreshed once),
and that every `seed:` request returns its status and text. On failure the run is `environment_blocked` with the failed
checks, not hundreds of failed tests: the orchestrator stops the dependent steps, and `main.py` / `tools.ci.run` exit 3.

**10.5 Selective execution** (`selective.py`): a fingerprint (`test_execution/fingerprint.json`, saved after every
full nightly / release run that succeeds) of pages (structural hash), AC statements, API endpoints (request shape),
spec texts and white-box source files, plus `git diff --name-only <base>` when given. A pull request runs the smoke
tests, the tests a change affects and every P0 test. Affected means: tests in a changed spec, plan tests of a changed
AC, tests of a design case on a changed page, and API tests of a changed endpoint or of a route whose source file
changed. With no stored fingerprint, everything runs.

**10.6 CI**: `python -m tools.ci.run --project <p> --stage pr|nightly|release [--git-base origin/main]
[--order-check] [--browsers ...] [--start-app <bench app>]`.

| Stage | What runs |
|---|---|
| `pr` | health check → smoke + affected + P0, chromium |
| `nightly` | health check → burn-in admission → whole suite on `execution.matrix` → optional order check → fingerprint saved |
| `release` | health check → whole suite; quality gates decide |

Every stage then triages failures and writes the report. Exit codes: 0 passed, 1 a quality gate failed (with no gates
configured: a gating test failed) or the run broke, 3 environment blocked. The stage summary is written to
`test_execution/reports/ci/<stage>_<ts>.json`. The templates upload the HTML and JSON reports, JUnit and traces.

## Benchmark

`python -m tools.benchmark.ci_bench` builds the project `bench_p10_ci` (buggy_shop on port 8775, real Chromium) and
runs the CI stages in four scenarios. Results: `benchmarks/results/2026-10-15_buggy_shop_phase10_ci.{json,md}`.
**15/15 checks pass.**

| Scenario | Stage | Exit | Result | Seconds |
|---|---|---|---|---|
| A: app down | pr | **3** | `environment_blocked` on the base-URL check; no test ran | 2.3 |
| B: fresh suite | nightly | **0** | burn-in admitted 5/5 tests (0 quarantined, 0 failing); order check over 5 tests: 0 order-dependent; fingerprint saved | 104.1 |
| C1: nothing changed | pr | **0** | 0 affected tests; only the 1 smoke test ran | 8.2 |
| C2: one spec edited | pr | **0** | 1 affected test (the edited `P_BS_002` spec); 2 ran (smoke + affected) against 5 nightly | 9.9 |
| D1: an always-failing test | release | **1** | 5 passed, 1 failed, the failure gates | 18.4 |
| D2: the same test quarantined | release | **0** | same results; the report lists the test under quarantine (status `failed`, not gating) | 27.8 |

Acceptance criteria: a CI run works end to end on buggy_shop (A–D), the quarantine round trip works (D, plus unit
tests for release and reset), and the health-check failure path is tested (A, plus unit tests).

## Fixed during the end-to-end run

The first full run passed 13 of 14 checks. Looking into the result turned up two real bugs and two wrong bench
expectations.

- **Bug: quarantine depended on Phase 11 enhanced reporting.** The quarantine split, `record_run` (stable-run
  counting, release, auto-quarantine of repeat-flaky tests) and the report listing sat inside ReportingAgent's quality
  section. That section returns early unless `reporting.enhanced` or `quality_gates` is set. In such a project nothing
  was counted or listed, although the CI exit code was right (it splits the results itself). Fix:
  `ReportingAgent._quarantine_section` runs on every report and writes `report["quarantine"]`. The quality section uses
  its gating results, and the HTML renders the section from the top-level key. `record_run` no longer creates an empty
  `quarantine.yaml` in projects that never needed one.
- **Bug: an app that is down took 97 s to block.** The role logins ran before the health check, and each login step
  waited for its 30 s timeout against the dead app. The base-URL check now runs before the role logins, and the full
  check (sessions, seed data) still runs after them. Scenario A: 97.3 s → 2.3 s.
- **Bench expectation: PR selection could not be seen.** The healing fixture tags every test `@smoke`, and a PR always
  runs the smoke tests, so both PR runs ran the whole suite. The check `pr < nightly + 1` (5 < 6) could not fail.
  Selection itself was right: 0 affected tests, then 1. The bench now keeps `@smoke` on the login test only and checks
  that C1 runs exactly the smoke test and C2 runs exactly smoke + affected, fewer than nightly.
- **Bench expectation: report lookup.** The bench looked for `*report*.json`, a pattern that matches no file. Report
  JSON files are `reports/json/<ts>_<project>.json`.

## Tests

`tests/unit/test_phase10_ci.py`, 17 tests:
- quarantine: round trip with release and reset; auto-add of repeat-flaky tests and the gating split; flaky counts read
  from reports;
- health check: app unreachable; expired session refreshed; missing seed data; base-URL-only mode; no `health_check`
  block;
- burn-in: mixed outcomes; all stable with the per-run cap; nothing new;
- order check: flags tests that depend on the run mode;
- selective: no fingerprint means run everything; affected tests by AC, page, endpoint and source; spec change;
- CI exit codes;
- ReportingAgent lists and updates the quarantine without enhanced reporting, and creates no file when there is
  nothing to quarantine.

Full unit suite (excluding the Phase 12 property tests): 2774 passed, 1 failed. The failure,
`test_exported_schemas_are_up_to_date`, was already there before Phase 10: `schemas/test_cases.v2.schema.json` was last
exported in Phase 3. It is regenerated in a separate commit.

## Still open

- **Sharded CI jobs across machines.** Today `execution.shards` shards within one job. Running shards as separate CI
  jobs needs a merge step for the Playwright blob reports and the MTA results before triage and reporting run once.
- **Flaky-rate trend chart.** The flaky rate is a quality gate and each run's history entry records the flaky count,
  but the report has no chart of the rate over time.
- The fixture suite is small (5 UI tests). Burn-in at 50 specs per night and the 3-mode order check have not been
  timed on a large suite.
- Selective execution maps changes to tests through the stored artifacts (plans, cases, API specs). A source change
  in a project without white-box `code_rules.json` reaches only the spec-text and git-path rules.
