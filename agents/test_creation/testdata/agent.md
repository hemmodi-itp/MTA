# TestDataAgent

Reads business scenarios and generates test data variants per scenario.

## Inputs
- `comprehension/business_scenarios.json`
- `comprehension/dom_elements.json`
- `comprehension/interaction_catalog.json` (optional — if available, used for field_name hints)

## Outputs
- `test_creation/test_data/test_data.json`
- `test_creation/test_data/test_data.md`

## Test variant types

| Variant | Behaviour |
|---------|-----------|
| `positive` | Realistic valid values for all fields |
| `empty` | All required fields blank |
| `whitespace` | Spaces/tabs only |
| `special_chars` | XSS/HTML injection characters |
| `sql_injection` | SQL strings |
| `wrong_format` | Wrong data type for field |
| `too_long` | One character over field max length |
| `at_boundary` | Exactly at field max length |
| `url_input` | URL as field value |
| `unicode` | Non-ASCII characters (emoji, CJK) |

Boundary max length is derived from field constraints in the scenario. Default to 255 if not specified.
Coverage is intentionally minimal by config default (`max_negative_cases`/`max_boundary_cases`/
`max_data_iterations` in `project.yaml`) — this table lists the full taxonomy the prompt can draw
from, not a fixed count generated every time. Read-only/navigation scenarios (no data-entry steps)
get an assertion/navigation-oriented positive dataset instead of form-field values — see
`prompt.py`'s "IF READ-ONLY SCENARIO" branch.

## Fallback behaviour (FailureClassifier)

- **RETRY** → rate limit or transient error (up to 2x with backoff)
- **NS_HTTP** → persistent rate limit or auth error: reroute to NSHTTPConnector
- **ALT_MODEL** → primary model unavailable: use claude-haiku-4-5-20251001
- **FALLBACK** → persistent validation error: `fallback_core.fallback_generate_test_data()` returns 3 fixed variants (positive, empty-field, boundary-max)

## Operational signal

`_llm_pipeline` also returns `coverage_pct`/`coverage_warning` — the percentage of scenarios in the
batch that got a usable positive dataset (or legitimately needed none, e.g. read-only scenarios with
no negative variants either). Logs a warning below 50%.
