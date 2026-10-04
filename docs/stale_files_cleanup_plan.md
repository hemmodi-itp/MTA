# Stale Files & Folders — Cleanup Backlog

First audit: 2026-07-15. **Updated 2026-10-03** (MTA redesign cleanup): the items in §2–§3 below were
deleted or untracked in that pass. Re-verify with a fresh grep (excluding `node_modules/`, `.venv/`
and `application_assets/`) before acting on anything still listed as open.

## 1. Removed in the 2026-10-03 cleanup

| Path | Why it was dead |
|---|---|
| `orchestrator/` (root: `context.py`, `contracts.py`, `recovery.py`, `__init__.py`) | Nothing outside the package imported it. Superseded by `agents/orchestrator/`. |
| `agents/test_execution/static_review/`, `agents/test_execution/agent_scoring/`, `tools/agent_eval/scoring.py` | Superseded by `agents/evaluation/{repository_review,compliance_scoring}`. Registry entries and `workflows/agents.yaml` flags removed too. |
| `contracts/{api_request_model,api_response_model,intent_model,page_model,scenario_model,testdata_model}.py` | Empty files. |
| `contracts/response_models.py`, `contracts/locator_model.py` | Never imported. (`request_models.py` and `state_models.py` are live and kept.) |
| `tools/html_report.py` | Shim that re-exported `tools/reports` and carried a stale, unimported copy of the code. |
| `tools/reports/` | Duplicate of `tools/test_execution/reports/` (ns_report.py and index_manager.py byte-identical, the rest older). `main.py` now imports `tools.test_execution.reports.ns_report`; that package is the single report implementation. |
| `tools/execution/__init__.py`, `tools/locator_repository.py`, `tools/page_repository.py`, `tools/page_asset_generator.py` | No importers (only their own unit tests, deleted with them: `test_locator_repository.py`, `test_page_repository.py`). |
| `tools/script_generator/` and `tools/test_creation/script_generator/{generate_script,export_scripts,models}.py` | Duplicate `GeneratedScript` models plus helpers nothing used. `tools/test_creation/script_generator/` now holds only `build_dom_locator_map.py` and `spec_renderer.py`. |
| `tools/convert_suites.py`, `tools/migrate_project_structure.py`, `tools/refactor_scenarios.py`, `tools/catalog/backfill_catalogs.py` | One-off scripts, already run and unreferenced. (`.claude/settings.json` still allowlists three of them; those entries are harmless but stale.) |
| `tools/healing/` | Only a leftover `__pycache__/`. |
| `PlaywrightScanner.execute_plan` / `_resolve_locator` (`tools/playwright_scanner.py`) | Dead methods. The only caller was a failing unit test, which was removed with them. |

## 2. Untracked (still on disk; now gitignored)

| Path | Files | Size |
|---|---|---|
| `node_modules/` (root) | 488 | 36.4 MB |
| `workflow_runs/` | 109 | 4.0 MB |
| `application_assets/**/test_execution/reports/` (HTML/JSON reports, Playwright traces, videos, screenshots) and `.dom_scan_checkpoint.json` / `.scan_checkpoint.json` | 2,993 | 537.5 MB |

`.gitignore` now also covers `node_modules/` (any level), `.aqp_cache/`, and `application_assets/**`
`test-results/`, `playwright-report/`, `traces/`, `screenshots/`, `*.webm` and `trace.zip`.

## 3. Still open — needs human judgment

| Path | Why it's flagged | Why it's not a simple delete |
|---|---|---|
| `tools/testdata/` vs `tools/test_creation/testdata/` | Two parallel "generate test data" implementations. | Both are live: `artifact_generator` uses the first, `TestDataAgent` the second. Consolidate; don't delete. |
| `connectors/aws/` | Only referenced by its own package `__init__.py`. | Owned by the connectors maintainers. Documented as future scaffolding (S3/SQS/Secrets Manager). |
| `cli_appevolve.py` (root) | Hardcoded to one project and superseded by `main.py`. | Still a working legacy CLI, and still referenced in `README.md` and `.claude/settings.json`. |
| `application_assets/myTestProjects/` vs `application_assets/projects/` | `PROJECTS_BASE` points at `projects/`, but real historical runs live in `myTestProjects/`. | Migrate or merge first; don't blind-delete. |
| `application_assets/projects/{my_project,proj,project,test_project,unknown}` | Test debris from before `tests/conftest.py` isolated `PROJECTS_BASE`. | Low priority. Confirm nobody is mid-experiment. |
| `application_assets/**/run_summary.json` | Generated per discovery run. | Kept tracked for now, next to the other generated-but-curated project artifacts (scenarios, intents, specs). Decide with the project owners. |

## 4. Docs needing a refresh (not deletion)

| Path | Issue |
|---|---|
| `docs/agentic_platform_and update.md` | Active ADK-migration plan, not yet implemented. Its first line asks to rename it to `docs/adk_migration_plan.md`. |
| `docs/playwright_enhancements.md` | Partly outdated: `expect.soft()` and `storageState` are already implemented. |
| `README.md` | Still documents `static_review`/`agent_scoring` and the old `agents/nsAgents/ns_registry.yaml` path. Maintained by the README owner. |

## 5. Local-only clutter (not tracked, no repo-size impact)

`logs/`, `playwright-report/`, `test-results/`, `__pycache__/` (repo-wide), `.pytest_cache/`. All are
gitignored and safe to delete locally at any time.
