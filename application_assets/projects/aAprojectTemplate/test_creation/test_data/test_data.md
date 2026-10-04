# Test Data

This folder holds the test datasets produced by **TestDataAgent**. These datasets are consumed by ScriptGenerationAgent to build each scenario's positive test plus its negative/boundary variants. All files here are written by the pipeline — do not edit them manually.

---

## What belongs here

- **`test_data.json`** — Machine-readable test data keyed by scenario ID (same scheme as `business_scenarios.json` — legacy `BS-001` or module-scoped `M01_BS_001`).
- **`test_data.md`** — This documentation file.

---

## Design: realistic coverage, not exhaustive matrices

TestDataAgent optimizes for **one well-chosen representative case per failure mode**, not an
exhaustive enumeration of every possible bad input. The positive dataset is what actually gets
exercised most (the full real user flow), so it gets the most care; negative/boundary data exists to
check the system degrades gracefully, and one solid representative case beats ten superficial ones.

How much negative/boundary data gets generated is controlled by `project.yaml`'s `test_generation:`
block (defaults: 1 negative case, 1 boundary case, up to 3 alternate data values tried within each):

```yaml
test_generation:
  max_negative_cases: 1
  max_boundary_cases: 1
  max_data_iterations: 3
```

Set `max_negative_cases: 0` / `max_boundary_cases: 0` to skip that category entirely for a project or
module — useful for read-heavy modules where negative/boundary input barely applies.

---

## Two scenario types

TestDataAgent classifies each scenario before generating data:

- **INTERACTIVE** — any step says "User enters/fills/types/selects/submits/uploads/chooses" → the
  scenario takes real data input. Fields get realistic values by type: `text | email | password |
  phone | number | select | date | textarea`.
- **READ-ONLY** — steps only say "User views/scrolls/reviews/browses/navigates to" or "System
  displays" → no data entry, but the scenario still gets a positive dataset describing what a passing
  test looks like, using these field types instead: `navigation` (section/anchor to reach), `assertion`
  (text that must be visible), `url` (expected URL/fragment), `count_min` (minimum item count).

---

## `test_data.json` format

```json
{
  "M01_BS_001": {
    "scenario_id": "M01_BS_001",
    "positive_dataset": [
      { "field_name": "username", "field_type": "email", "value": "testuser@example.com" },
      { "field_name": "password", "field_type": "password", "value": "ValidPass123!" }
    ],
    "negative_variants": [
      {
        "variant_type": "negative",
        "description": "Invalid or missing required input",
        "iterations": [
          {
            "fields": [
              { "field_name": "username", "field_type": "email", "value": "" },
              { "field_name": "password", "field_type": "password", "value": "" }
            ],
            "expected_error": "Username and password are required"
          }
        ]
      },
      {
        "variant_type": "boundary",
        "description": "Input at/over the field length limit",
        "iterations": [
          {
            "fields": [
              { "field_name": "username", "field_type": "email", "value": "a-value-exactly-at-max-length@example.com" }
            ],
            "expected_error": null
          }
        ]
      }
    ]
  }
}
```

Notes on the shape:
- `positive_dataset` is a **list** of typed fields, not a single flat key/value object — this is what
  lets the same schema describe both INTERACTIVE fields and READ-ONLY navigation/assertion targets.
- Each `negative_variants[]` entry is one failure mode (`variant_type: "negative"` or `"boundary"`),
  containing up to `max_data_iterations` `iterations[]` — alternate value sets for that *same* failure
  mode, exercised in a single generated test via a loop rather than one test per iteration.
- The max field length used for boundary data comes from constraints stated in the BRD; if none is
  stated, TestDataAgent defaults to 255 characters.

---

## Produced by

TestDataAgent reads `comprehension/business_scenarios.json` to understand which fields each scenario touches (or, for read-only scenarios, what the expected_result implies), and generates the positive dataset plus the configured number of negative/boundary variants.

## Consumed by

ScriptGenerationAgent reads `test_data.json` alongside `scenario_element_map.json` to write each scenario's `.spec.ts` — one `test()` for the positive flow, and one `test()` per negative/boundary variant (looping over that variant's iterations internally, not one test per iteration).

---

## File types allowed

`.json` and `.md` only.
