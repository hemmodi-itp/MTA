import string

INTENT_GENERATION_PROMPT = string.Template("""
$skill_header

You are analyzing business scenarios to extract atomic UI test intents.

For each step in the scenarios below, identify the atomic UI action it represents.
Produce a DEDUPLICATED list of intents — if the same action on the same element appears
in multiple scenarios, include it only once and list all source scenario IDs.

Action types:
- fill     — user types text into an input field
- click    — user clicks a button, link, or interactive element
- select   — user selects from a dropdown or radio group
- navigate — user navigates to a URL or page
- verify   — system checks / assertion (element visible, URL changed, message shown)

Rules:
- intent_name must be snake_case (e.g. fill_email, click_login_button, verify_dashboard_url)
- Deduplicate: same element + same action type = one intent (different values are NOT different intents)
- source_scenarios must list every BS-XXX id that contains this step
$existing_intents_summary
== Project Format Reference (match terminology and naming style) ==
$md_context

== Business Scenarios to process (generate intents ONLY for these) ==
$scenarios_json

Return ONLY valid JSON in this exact format, no markdown fences:
{
  "intents": [
    {
      "intent_name": "navigate_to_login",
      "action": "navigate",
      "description": "Navigate to the login page",
      "source_scenarios": ["BS-001", "BS-002"]
    },
    {
      "intent_name": "fill_email",
      "action": "fill",
      "description": "Enter email address in the email input field",
      "source_scenarios": ["BS-001"]
    }
  ]
}
""")

TESTCASE_MAPPING_PROMPT = string.Template("""
$skill_header

You are mapping business scenarios to ordered sequences of UI test intents.

For each test case produce:
- test_case_name: a concise descriptive name (e.g. "Login with valid credentials")
- business_scenario_id: the exact BS-XXX id from the input
- test_case_type: one of: positive | negative | boundary | out_of_box
- steps: an ordered list of intent IDs (INT-XXX) from the available intents list
- expected_result: what the system should show or do after the last step
$existing_tc_summary
== Project Format Reference (match terminology and naming style) ==
$md_context

Rules:
- Produce approximately 10 test cases in total across all scenarios.
- Assign a test_case_type to every test case using ONLY these values:
    positive    — happy-path, all valid inputs, expects success
    negative    — at least one invalid or missing input, expects an error or rejection
    boundary    — inputs at the exact edge of allowed limits (max length, zero, empty-but-required)
    out_of_box  — unexpected/creative inputs a real user might try accidentally (emoji, scripts, URLs in wrong fields)
- Distribute types across the full set — targets:
    at least 3 positive, at least 2 negative, at least 1 boundary, at least 1 out_of_box
- The same business_scenario_id may appear in multiple test cases of different types.
- EVERY test case must include at least one fill, click, or select step.
  Do NOT generate navigate-only or verify-only test cases.
  If a scenario has no interactive intents, combine it with an adjacent scenario that does.
- Use ONLY intent IDs from the available intents list below.
- Order steps to match the natural flow of the scenario.

Business Scenarios:
$scenarios_json

Available Intents:
$intents_json

Return ONLY valid JSON in this exact format, no markdown fences:
{
  "test_cases": [
    {
      "test_case_name": "Login with valid credentials",
      "business_scenario_id": "BS-001",
      "test_case_type": "positive",
      "steps": ["INT-001", "INT-002", "INT-003", "INT-004", "INT-005"],
      "expected_result": "User is redirected to the dashboard page"
    },
    {
      "test_case_name": "Login with empty email",
      "business_scenario_id": "BS-001",
      "test_case_type": "negative",
      "steps": ["INT-002", "INT-003", "INT-005"],
      "expected_result": "Validation error: email address is required"
    }
  ]
}
""")
