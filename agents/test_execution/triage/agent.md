# TriageAgent

Phase 6.1. Runs after `ui_execution` and before `healing`: decides, for every failed test, whether the **product**
or the **test** is wrong — healing may only touch test defects, so a product bug is never patched away.

## Inputs
- `project_name`; `report_json` (default: the latest `test_execution/reports/json/*_results.json`)
- `project.yaml` → `healing.flaky_rerun` (default true), `healing.triage_llm` (default true), the base URL
- `known_issues.yaml` at the project root (optional)
- earlier `*_results.json` reports in the same folder (history evidence)

## Outputs
- `test_execution/reports/triage.json` — `{report, counts, refined, tests: [{spec_file, test_name, project, status,
  error, verdict, evidence[], recovered?, llm?}]}`
- `test_execution/reports/defects.json` — the `product_defect` entries

## Behaviour
1. **Deterministic classification** (`tools/triage/triage.py`): flaky → known_issue → environment (infrastructure
   errors, 502/503/504) → product_defect (5xx, new console errors, HTTP status in the error) → test_defect.data →
   test_defect.locator → product_defect (assertion failed with resolving locators; then a 4xx response) → unknown.
   Responses a test mocked itself (`network_error` annotations marked `(mocked)`) are ignored. Evidence also notes the
   test's run history and whether it passes in another browser of the same run.
2. **environment**: health check of the base URL; unhealthy → reported as is; healthy → one re-run; a pass is
   `recovered`, a different failure is classified again.
3. **flaky**: every remaining failure is re-run with `--repeat-each=3`; any pass → `flaky`.
4. **unknown** → one LLM call (`prompt.py`); its verdict is kept only if every quote is found in the error.

## Failure modes
- No report → `status: skipped`. Re-run or LLM errors never fail the step: the verdict stays as classified.
- HealingAgent reuses `triage.json` when its `report` matches the report being healed; otherwise it triages itself.
