# ArtifactGeneratorAgent

Bridges ComprehensionAgent output to execution-ready YAML artifacts.

## Modes

| Mode | Step | Input | Output |
|------|------|-------|--------|
| `intents` | `artifact_generator_intents` | business_scenarios.json | artifacts/intents.yaml |
| `testcases` | `artifact_generator_testcases` | intents.yaml + test_data.json | intents.yaml (enriched), test_cases.yaml, test_suite.yaml |

---

## Pre-execution (mandatory, both modes)

Before any LLM call, the agent loads a `ProjectArtifactContext` which reads:

1. `artifacts/intents.yaml` — existing intents (IDs, names, covered scenario IDs)
2. `project_state["test_cases"]` — existing test cases from the persistent state
3. `comprehension/business_scenarios.md` — capped to 1 500 chars for format/terminology guide
4. `test_data/test_data.md` — capped to 1 500 chars for field-name and style guide

All context injected into LLM prompts is compacted to ≤ 4 000 chars total.

---

## Intents mode

1. Load all business scenarios from `comprehension/business_scenarios.json`.
2. Determine `covered_scenario_ids` from `ctx.covered_scenario_ids` (scenarios already referenced by existing intents).
3. Filter to `uncovered_scenarios` — scenarios not yet covered.
4. **If zero uncovered** → return `status: success, skipped: true` immediately. No LLM call.
5. Build extra prompt context:
   - `existing_intents_summary` — compact list of existing intents (dedup hint, ≤ 800 chars)
   - `md_context` — capped business_scenarios.md (format/terminology guide)
6. Call LLM only for the uncovered scenarios.
7. **Renumber** new intents starting from `len(existing) + 1` (INT-N+1, INT-N+2, …).
8. Ground new intents with DOM locators from `discovery/dom_intents.json`.
9. **Merge**: existing `IntentDefinition` objects + new ones → write back to `intents.yaml`.
10. Never delete existing intents.

---

## TestCases mode

1. Load `intents.yaml` (must exist — fail fast if absent).
2. Enrich intents with test data values from `test_data.json`.
3. Load all business scenarios.
4. Build extra prompt context:
   - `existing_tc_summary` — compact list of existing test cases (dedup hint, ≤ 800 chars)
   - `md_context` — capped business_scenarios.md + test_data.md concatenated
5. Call LLM for all scenarios (SemanticDedupAgent is the final dedup guard).
6. Validate, generate suite, export artifacts.
7. Never delete existing test cases from `project_state`.

---

## Outputs

```
application_assets/projects/{project}/artifacts/
  intents.yaml          — merged existing + new intents
  test_cases.yaml       — newly proposed test cases (before dedup)
  test_suite.yaml       — suite referencing all test case IDs
```

---

## Failure modes

| Condition | Behaviour |
|-----------|-----------|
| `comprehension_status == "failed"` in upstream state | Return `status: failed` immediately |
| `intents.yaml` missing in testcases mode | Return `status: failed` |
| LLM JSON parse error | Return `status: failed` with error detail |
| Zero uncovered scenarios (intents mode) | Return `status: success, skipped: true` |
