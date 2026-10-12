# TestDesignAgent

Phase 3 of the MTA improvement plan. Derives test cases **systematically with named techniques**, prioritises
them by risk and selects them within an explicit budget, instead of 1 positive + 1 negative + 1 boundary per
scenario. Output: `test_creation/test_cases.json`. ScriptGeneration then implements exactly the selected cases.

## Contract

| | |
|---|---|
| Registry key / step | `test_design` — runs after `testdata`, before `semantic_map` |
| Switch | `test_generation.profile` in project.yaml (`smoke` / `standard` / `thorough` / `exhaustive`). Absent → skipped, nothing written, legacy generation unchanged. Requires `requirements.enabled: true`. |
| Inputs | `test_comprehension/requirements.json` (required), `business_scenarios.json`, `form_model.json`, `app_map.json`, `permission_matrix.json` (Phase 2, each optional), `test_creation/test_data/test_data.json`, previous `test_cases.json` (change fingerprint), project.yaml (profile, budget, auth roles, module setups, safety) |
| Outputs | `test_creation/test_cases.json` (v2, contract `test_cases`); new `_source: form_model` entries in `test_creation/locator_map.json` |
| Result | `{status, skipped?, profile, summary, budget, conflicts, llm, output: {test_cases, locator_keys_added}, warnings}` |

## Behavior

1. **Generators** (`tools/test_design/`, pure Python, deterministic): `ep`, `bva` (3-value, incl. dates and
   file sizes), `decision_table` (built and collapsed in code from LLM-extracted conditions), `state_transition`
   (0-switch, invalid deep links / back / refresh, 1-switch), `pairwise` (all-pairs), `use_case` (per-AC main and
   exception flows + scenario journeys — the coverage floor), `crud`, `error_guessing` (data catalog
   `catalog/error_guessing.yaml`), `role_matrix` (every permission-matrix page cell; role-boundary actions).
   Constraint precedence: DOM > BRD AC > observed validation > default (flagged).
2. **Linking**: generator ACs → content-word linking → LLM links (validated). Role-matrix cases are linked by rule.
3. **LLM** (one schema-validated call per module, `design_llm: false` to disable): decision-table rules,
   negative paths, AC links, ≤ 6 domain cases. Additive only. Extra cases go through `SemanticDedupAgent`
   against the deterministic set, which is never on the removable side.
4. **Risk** `impact × likelihood` → P0–P3. **Assignment** of each case to a scenario whose module role can reach
   its page (role cases → a module that signs in as that role).
5. **Selection**: profile filter → every P0 → coverage floor (≥ 1 case per testable AC, plus a negative where
   one exists) → descending risk within `max_tests` / `max_runtime_minutes`. Cut cases are listed with reason
   `budget` (or `no_scenario`).
6. **BRD vs observed**: a probe that saw the app accept what an AC rejects is listed in `conflicts[]`; the case
   keeps the BRD oracle.
7. **Locators**: fields and submit buttons of targeted forms are merged into `locator_map.json` with their
   `_page_url`; ScriptGeneration validates them live on that page.

## Failure modes

- LLM unavailable / invalid twice → that module is `degraded`, deterministic cases only (`status: partial`).
- Semantic dedup failure → LLM cases kept (fail-open; they are additive).
- P0 + floor cases above the budget → kept, `budget.respected: false`, `status: partial` (never hidden).
- Missing Phase 2 artifact → its generators produce nothing; listed in `limitations`.
