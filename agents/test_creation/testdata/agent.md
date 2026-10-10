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

## Security-probe payloads (Phase 0.5)

Unless the project's `SafetyPolicy` allows security probes (`safety.allow_security_probes:
true` **and** `environment` local/dev/staging — prod and an undeclared environment always
refuse), negative/boundary iterations whose values carry an active attack payload (XSS,
SQL/NoSQL injection, path traversal, template/command injection —
`tools/safety/payloads.py`) are removed after generation; a variant left with no
iterations is removed too. Positive datasets are never altered (a payload there is
reported only). Every removal is returned as `security_probe_drops` and written to
`human_review_queue.json` (`kind: "safety_drop"`).

## Artifact contract (Phase 0.7)

`test_data.json` is written as a schema_version 2 envelope —
`{"schema_version": 2, "artifact": "test_data", "datasets": [...]}` — by both the LLM path
and the Python fallback (whose old shape is canonicalised by the v1→v2 migration). Readers
use `contracts.artifacts.load_records`, which accepts v1 lists, v2 envelopes and legacy
id-maps.

## Capped variants are recorded (Phase 1)

Variants the LLM proposed but `test_generation` caps removed are counted per scenario in
`capped_variants: {"negative": n, "boundary": m}` (serialised only when non-zero). The traceability report uses
it to say an acceptance criterion went untested for `budget`. The caps themselves are unchanged.
