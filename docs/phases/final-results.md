# MTA — Final Results (2026-10-13)

Benchmarks: `benchmarks/results/2026-10-13_buggy_shop_final.md` (commit `6b4cfcc`, 61 tests, all 22 seeded bugs enabled one at a time, 2 bug-free runs) and `2026-10-13_buggy_bot_phase9.md` (mock mode, seed 7).

**Caveat:** the buggy_shop run reused the existing generated suite (`--skip-generate`, no LLM tokens). That suite was generated before Phases 5–7 existed, so oracle hardening, the assertion linter and the a11y/security specs are **implemented but not reflected** in these numbers. A full regeneration run is needed to measure them.

## KPIs (plan §7)

| KPI | Phase 0 baseline (as-is / collision fix) | Now | Target |
|---|---|---|---|
| Requirement (AC) coverage | 0.0% (0/27) / 0.0% | **25.9%** (7/27) | ≥ 90% |
| Seeded-bug detection rate | 0.0% (0/22) / 4.5% (1/22) | **13.6%** (3/22: BUG_01, 18, 21) | ≥ 80% |
| False-failure rate (bug-free build) | 70.0% / 28.3% | **18.0%** | < 3% |
| Flaky rate | 0.0% / 0.0% (2 runs) | **1.6%** | < 2% |
| Weak-oracle count | n/a | n/a (suite predates the Phase 5 linter) | — |
| AI-agent weakness detection (buggy_bot) | n/a | **14/14** mock, 0 false positives; real LLM 7/14 on verified verdicts (Phase 9 run) | — |
| LLM calls per run (execution) | 203–223 (incl. generation) | 0 (generation not re-run) | ≤ 1.5× baseline |

Notes: the 3 bugs caught are the validation/boundary bugs whose ACs have implemented tests. 13 of 22 bugs are targeted by the Phase 3 design but only 6 are implemented in specs, and 20 ACs have no executed test. The coverage gap, not the oracles, is the main limit on detection. With the new gates (`p0_pass_rate: 100`, `requirement_coverage: 90`), this build would **FAIL** (coverage 25.9% < 90%).

## What's implemented

- **Phase 0**: audit, buggy_shop (22 seeded bugs) and buggy_bot benchmarks, scoring runner, safety rails, base-URL resolution, artifact contracts.
- **Phase 1**: requirements.json, AC-linked and tagged tests, traceability.json with "why untested" reasons.
- **Phase 2**: deep discovery (crawl, form probes, network, roles, baseline).
- **Phase 3**: test-design techniques (EP, BVA, decision table, state transition, role matrix, use case) with a budgeted profile.
- **Phase 4**: Playwright runtime: config, per-role auth, MTA reporter, shards, tags, fixtures, test.step, web-first waits, flaky classification.
- **Phase 5-lean**: new oracle actions, assertion linter, console-error check, oracle prompt.
- **Phase 6-lean**: deterministic failure triage; healing limited to test defects (propose mode).
- **Phase 7-mini**: generated axe a11y specs and passive security specs.
- **Phase 9**: AI-agent / LLM testing: 15 dimensions, golden datasets, LLM judge with calibration, Wilson-bound gates, regression.
- **Phase 11-lean**: executive summary, traceability CSV, "not tested & why", defect list with evidence links, quality gates with a non-zero exit code.

## Roadmap (from docs/backlog.md)

- **Phase 5**: grey-box API state checks, ARIA snapshots, count/persistence/download/new-tab/storage checks, fault injection, BRD-vs-observed conflict handling, positive-submit linter rule.
- **Phase 6**: locator fingerprinting, blast-radius re-run and burn-in for heals, model fallback, heal audit log, known issues, flaky re-run, triage as its own agent, environment verdict.
- **Phase 7**: visual regression, performance budgets, responsive/browser matrix, resilience, i18n, active security probes, keyboard/focus a11y, pipeline wiring for the NFR generator.
- **Phase 11**: risk areas and trend, defects by severity, coverage dashboard, XLSX/interactive matrix, richer evidence, Jira/ADO export, remaining gates, CI wiring of the gate exit code.
- **Next highest-value step**: regenerate the buggy_shop suite with Phases 5–7 enabled and close the AC coverage gap (20 ACs untested). Both directly drive detection rate.
