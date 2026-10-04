# Test Data

This folder holds the test datasets produced by **TestDataAgent**. These datasets are consumed by ScriptGenerationAgent to drive the 8-10 test variants per business scenario.

## What belongs here

- `test_data.json` — Machine-readable test datasets keyed by business scenario ID (aligned 1:1 with `BS-001..N` from comprehension). Each entry contains one positive dataset and **8-10 named negative/boundary variants**.
- `test_data.md` — Human-readable summary of what was generated (this file).

## Test variant types (8-10 per scenario)

| Variant | Description | Example |
|---------|-------------|---------|
| `positive` | All required fields with realistic valid values | `"Water Flow Meter"`, `"john@example.com"` |
| `empty` | All required fields left blank | `""` |
| `whitespace` | Fields contain only spaces/tabs | `"   "` |
| `special_chars` | XSS / HTML injection | `<script>alert('xss')</script>` |
| `sql_injection` | SQL strings | `' OR '1'='1` |
| `wrong_format` | Structurally invalid for field type | `"12345"` for an email field |
| `too_long` | One character over the maximum allowed length | 256-char string for a 255-char field |
| `at_boundary` | Exactly at the maximum allowed length | 255-char string for a 255-char field |
| `url_input` | URL as field value | `https://evil.com/redirect` |
| `unicode` | Non-ASCII characters | `あいうえお`, `🔥🎉` |

The boundary max length is derived from field constraints described in the business scenario. If no constraint is stated, default to 255 for text fields.

## `test_data.json` format

```json
{
  "TD-007": {
    "scenario_id": "BS-007",
    "scenario_name": "Search for Specific Products",
    "positive_dataset": {
      "description": "Valid search term that returns results",
      "data": { "search_term": "Water Flow Meter" }
    },
    "negative_variants": [
      {
        "variant_id": "BS-007-NEG-001",
        "variant_type": "empty",
        "description": "Empty search term",
        "data": { "search_term": "" }
      },
      {
        "variant_id": "BS-007-NEG-002",
        "variant_type": "special_chars",
        "description": "XSS injection in search field",
        "data": { "search_term": "<script>alert('xss')</script>" }
      }
    ]
  }
}
```

## Produced by

TestDataAgent reads `comprehension/business_scenarios.json` and optionally `comprehension/interaction_catalog.json` to understand which fields each scenario touches. It generates realistic positive values and adversarial negative variants for every field.

## Consumed by

ScriptGenerationAgent reads `test_data.json` alongside `scenario_element_map.json` to produce parameterised TypeScript `.spec.ts` files with one `test()` block per variant.

## File types allowed

`.json` and `.md` only.
