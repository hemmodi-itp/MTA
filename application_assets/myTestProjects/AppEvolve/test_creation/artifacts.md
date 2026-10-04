# Test Creation Artifacts

This folder holds the structured artifacts produced by the **test creation module** (Module 2). These are the intermediate and output files between business-level comprehension and executable Playwright test specs.

## What belongs here

- `scenario_element_map.json` — Semantic mapping of each business scenario to the DOM elements relevant to its steps. Produced by SemanticMapAgent. Consumed by ScriptGenerationAgent to scope the LLM prompt to 3-7 elements per scenario rather than all 63+.
- `test_suite.json` — Suite manifest tracking every `.spec.ts` file and its status (`new`, `existing`, `healed`, `healed_fallback`, `degraded_fallback`). Updated after each run and after healing.

## `scenario_element_map.json` format

```json
{
  "BS-007": {
    "scenario_title": "Search for Specific Products",
    "relevant_elements": [
      {
        "locator_id": "LOC-0002",
        "playwright_expr": "page.getByPlaceholder('Search Products ...')",
        "relevance": "primary search input"
      }
    ]
  }
}
```

## `test_suite.json` format

```json
{
  "project": "myProject",
  "generated_at": "2026-06-17T10:00:00Z",
  "total_scenarios": 10,
  "new_additions": ["test_BS-007_search_for_specific_products.spec.ts"],
  "specs": [
    {
      "spec_id": "BS-007",
      "scenario_title": "Search for Specific Products",
      "file": "test_BS-007_search_for_specific_products.spec.ts",
      "test_types": ["positive", "negative", "boundary"],
      "test_count": 8,
      "status": "new",
      "tier_used": 0,
      "fallback_route": null,
      "last_run": null,
      "last_result": null
    }
  ]
}
```

`tier_used` values: `0` = primary LLM, `1` = NSHTTPConnector, `2` = Python fallback.  
`status` values: `new`, `existing`, `healed`, `healed_fallback`, `degraded_fallback`.

## Deprecated (removed in this architecture)

The following files from the previous architecture are no longer produced:
- `intents.yaml` — replaced by `interaction_catalog.json` (docs only, in `comprehension/`) and `scenario_element_map.json`
- `test_cases.yaml` — replaced by `test_suite.json`
- `test_suite.yaml` — replaced by `test_suite.json`
- `locators.json` — eliminated; Playwright semantic locators come directly from `dom_elements.json`

## File types allowed

`.json` only. Test scripts are in `test_scripts/`. BRD inputs are in `inputs/`.
