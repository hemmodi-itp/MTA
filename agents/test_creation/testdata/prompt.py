"""
prompt.py — LLM prompt templates for the TestData Agent.

Templates use Python's string.Template syntax ($variable).
Call template.safe_substitute(**kwargs) to render.
"""

from string import Template

TEST_DATA_GENERATION_PROMPT = Template(
    """$skill_header

You are generating test data for a single business scenario.
$existing_format_guide
== Scenario ==
ID: $scenario_id
Title: $title
Actor: $actor
Business Objective: $business_objective

Preconditions:
$preconditions_json

Steps:
$steps_json

Expected Result: $expected_result

== Scenario Type Detection ==

First, classify this scenario:
- INTERACTIVE: ANY step says "User enters", "User fills", "User types", "User selects", "User submits", "User uploads", "User chooses" → user is providing data input
- READ-ONLY: Steps only say "User views", "User scrolls", "User reviews", "User browses", "User navigates to", "System displays", "User clicks link/button to navigate", "User reads" → user is observing or navigating, no data entry

== Task ==

The emphasis of this test data is REALISTIC COVERAGE, not exhaustive matrices:
the positive dataset is what actually gets exercised most, so make it count.
Negative/boundary data exists to check the system degrades gracefully — one
well-chosen representative case (with a couple of alternate values) is enough.
This applies to BOTH scenario types below — READ-ONLY scenarios still need a
positive dataset (navigation/assertion targets) and at least one negative
case; they are not exempt from having test data.

$fill_fields_hint

--- IF INTERACTIVE SCENARIO ---

1. Identify every INPUT FIELD the steps require (e.g. username, password, amount, date).
   If a step says "User enters X" or "User fills Y" — X and Y are fields.

2. For each field determine its type:
   text | email | password | phone | number | select | date | textarea

3. Generate a POSITIVE DATASET with realistic, valid values that reflect how a
   real user would actually fill this in (e.g. real-looking email, strong
   password, valid phone number).

4. Derive the MAX FIELD LENGTH from field constraints mentioned in the scenario.
   If not specified, default to 255 characters.

--- IF READ-ONLY SCENARIO ---

1. Generate a POSITIVE DATASET of navigation/assertion fields that define what
   a PASSING test looks like — 3-6 fields drawn directly from the scenario's
   expected_result and steps. Use these field_type values:
   - "navigation"  — the section name or anchor the test must scroll/navigate to
   - "assertion"   — text content that MUST be visible on the page for the step to pass
   - "url"         — expected URL or URL fragment after navigation
   - "count_min"   — minimum number of items/elements that must appear (value is a number as string)

   Name fields descriptively: scroll_target, expected_heading, expected_keyword,
   expected_url, min_items_count, etc.

2. Pick the single most representative failure mode for this scenario — e.g.
   the key section/heading being absent, navigation landing on the wrong
   page/404, or expected content not rendering — and express it as a
   "negative" variant whose iteration fields invert/corrupt the matching
   positive field (e.g. expected_heading value = "" or "WRONG HEADING").

For BOTH scenario types:

5. Generate AT MOST $max_negative_cases "negative" variant(s) and AT MOST
   $max_boundary_cases "boundary" variant(s) — no more. Pick whichever single
   failure mode is most representative/likely for this scenario rather than
   enumerating every possible bad-input/failure category.

   - "negative" variant: invalid input a real user might submit by mistake
     (empty required field, wrong format, obviously invalid value) — or, for
     READ-ONLY scenarios, a corrupted/missing version of a positive field.
   - "boundary" variant: input at or just past a length/range limit
     (not typically applicable to READ-ONLY scenarios — omit if none fits).

   Within EACH variant, provide up to $max_data_iterations "iterations" —
   alternate value sets for the same failure mode (e.g. empty vs. malformed
   for "negative"; at-limit vs. over-limit for "boundary"). These iterations
   are exercised in a single test, not one test each, so keep them tight and
   meaningfully different from one another rather than padding the count.

6. For each iteration provide the expected_error message the system SHOULD show.

Return ONLY a valid JSON object in this exact structure. No markdown, no explanation.

{
  "scenario_id": "$scenario_id",
  "positive_dataset": [
    {
      "field_name": "field_name_snake_case",
      "field_type": "email",
      "value": "realistic.value@example.com"
    }
  ],
  "negative_variants": [
    {
      "variant_type": "negative",
      "description": "Invalid or missing required input",
      "iterations": [
        {
          "fields": [
            {
              "field_name": "field_name_snake_case",
              "field_type": "email",
              "value": ""
            }
          ],
          "expected_error": "Email is required"
        }
      ]
    },
    {
      "variant_type": "boundary",
      "description": "Input at/over the field length limit",
      "iterations": [
        {
          "fields": [
            {
              "field_name": "field_name_snake_case",
              "field_type": "email",
              "value": "a-value-exactly-at-max-length@example.com"
            }
          ],
          "expected_error": null
        }
      ]
    }
  ]
}

Rules:
- field_name must be snake_case.
- Every iteration must include ALL fields from the positive dataset — use the
  bad value for the field under test, keep valid values for the rest, unless
  the failure mode targets all fields simultaneously (e.g. all blank).
- variant_type must be exactly "negative" or "boundary" — nothing else.
- Return at most $max_negative_cases variant(s) with variant_type "negative"
  and at most $max_boundary_cases variant(s) with variant_type "boundary".
- Each variant's iterations list must have at most $max_data_iterations entries.
- Return ONLY the JSON object — no markdown fences, no commentary.
"""
)
