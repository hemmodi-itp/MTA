"""prompt.py — LLM prompt templates for ScriptGenerationAgent.

The LLM no longer writes Playwright TypeScript directly. It picks from a
fixed action-verb vocabulary (ALLOWED_ACTIONS in agent.py, mirroring
application_assets/_shared/runtime/ActionEngine.ts) and named locator keys
(this scenario's slice of the project's locator_map.json) or a reusable
named flow (flows.json), and returns a JSON test plan. A deterministic
renderer (tools/test_creation/script_generator/spec_renderer.py) then turns
that plan into the actual .spec.ts file — no LLM-authored code ever reaches
disk.

Four few-shot examples are embedded directly in ACTION_LIBRARY_PROMPT so the
model is anchored to concrete shapes from the first call, rather than
inferring the format purely from the schema description — each models a
different flow shape real scenarios take:
  1. A dependent multi-step form flow (login) written out explicitly
     (enterText/enterText/click/verify), not hidden behind useFlow — most
     projects have no flows.json at all, so the model needs to see the
     actual step sequence at least once, not just a shortcut around it.
  2. Negative + boundary variants of a single-field flow, plus a soft
     assertion.
  3. A sibling/equal-weight cluster (e.g. a nav bar's several links): ONE
     positive test that walks every sibling in sequence
     (click → verify → go back → next), not one test per link.
  4. A prompt/chat submit-and-verify-response flow (enterText → submit →
     verify a result appeared) — the shape most AI-assistant-style UIs need
     and the two form-flow examples above don't cover.
"""

from string import Template

ACTION_LIBRARY_PROMPT = Template("""
You are a QA engineer planning a Playwright test for ONE business scenario.
You do NOT write TypeScript or any Playwright code. You return a JSON test
plan built ONLY from the actions, locators, and flows listed below — a
separate, non-AI step turns your plan into the actual test file.

== Scenario ==
$scenario_json

== Test Data ==
$test_data_json
(each negative/boundary variant may carry an "iterations" array — up to $max_data_iterations
alternate value sets for that same failure mode)

== BASE_URL ==
$base_url

== Allowed actions (use ONLY these — the exact string in "action") ==
$valid_actions_json

== Allowed locator keys for THIS scenario (use ONLY these in "locator_key") ==
$valid_locators_json
(when present, "cluster" groups locators that belong to the same functional
area — e.g. username/password/forgot-password all in one "login" cluster —
and "confidence" (0-1) is how relevant that locator is to this scenario;
"action"/"expected_result" describe what the underlying UI intent actually
does. Not every locator will have these — a plain dom_elements.json-only
project won't. Absence of these fields changes nothing about which keys are
allowed.)

== Allowed reusable flows (use ONLY these in a "useFlow" step's "flow") ==
$valid_flows_json

== Output format ==

Return ONLY a raw JSON object (no markdown fences, no explanation) matching:

{
  "tests": [
    {
      "name": "positive — valid form submission succeeds",
      "type": "positive",
      "steps": [
        {"action": "navigate"},
        {"action": "useFlow", "flow": "login", "args": {"username": "standard_user", "password": "secret_sauce"}},
        {"action": "enterText", "locator_key": "search_box", "value": "Water Flow Meter"},
        {"action": "click", "locator_key": "search_button"},
        {"action": "verifyVisible", "locator_key": "results_list", "message": "Results must appear after a valid search"}
      ]
    }
  ],
  "missing_actions": [],
  "missing_locators": []
}

== Step shapes by action ==

- Most actions: {"action": "<verb>", "locator_key": "<key>", "value": "<optional>", "message": "<optional, for verify* actions>"}
- "navigate": {"action": "navigate", "value": "<optional relative or absolute URL — omit to use BASE_URL>"}
- "verifyUrlContains" / "verifyTitleContains": {"action": "verifyUrlContains", "value": "<substring>", "message": "..."} —
  no locator_key (page-level, like verifyUrl/verifyTitle). Use these instead of the exact-match verifyUrl/verifyTitle
  whenever the scenario doesn't itself pin an exact literal — see "Lessons learned" below.
- "waitForTimeout": {"action": "waitForTimeout", "value": <milliseconds, a number>}
- "verifyCount": {"action": "verifyCount", "locator_key": "<key>", "value": <count, a number>, "message": "<optional>"}
- "verifyNoPageErrors": {"action": "verifyNoPageErrors", "message": "<optional>"} — no locator_key; asserts no
  uncaught JS error/exception occurred on the page since the test started. Use sparingly — only when the
  scenario is specifically about page stability, not on every test.
- "pressKey": {"action": "pressKey", "locator_key": "<key or null for a page-level key press>", "value": "<key name, e.g. Enter>"}
- "dragAndDrop": {"action": "dragAndDrop", "locator_key": "<source key>", "target_locator_key": "<target key>"}
- "useFlow": {"action": "useFlow", "flow": "<flow name>", "args": {"<param>": "<value>", ...}} — args must supply every
  parameter the flow declares, using literal values (do not pass "{{...}}" template syntax — that is only used
  inside flows.json itself, never in a test's own steps).
- Every "verify*" action MUST carry a "message" — a short, plain-English description of what the assertion checks.
- Any "verify*" action MAY carry "soft": true to collect the failure and keep running the rest of the test
  instead of stopping immediately — use for a handful of related checks in the same test where one failing
  shouldn't hide the others (e.g. several field-level checks after one form submission), not as a default.

== Example 1 — dependent multi-step form flow (login), written out explicitly ==

Most projects have an empty or near-empty "Allowed reusable flows" list — do not wait for a "login"
flow to exist. Here is the explicit sequence to write when it doesn't: enterText focuses AND fills a
field in one step (no separate click needed before it); click is for buttons/links only.

Scenario:
{
  "scenario_id": "M01_BS_001",
  "title": "Standard user login with valid credentials",
  "business_objective": "Verify a registered user can authenticate and reach the inventory page",
  "actor": "Registered user",
  "preconditions": ["User is on the login page"],
  "steps": [
    "User enters a valid username and password",
    "User clicks the login button",
    "User is redirected to the inventory page"
  ],
  "expected_result": "User lands on the inventory page",
  "module_id": "M01"
}

Test Data (abridged):
{
  "positive_dataset": [{"field_name": "username", "value": "standard_user"}, {"field_name": "password", "value": "secret_sauce"}],
  "negative_variants": [
    {"variant_id": "NEG-001", "description": "wrong password", "iterations": [
      {"fields": [{"field_name": "username", "value": "standard_user"}, {"field_name": "password", "value": "wrong_password"}],
       "expected_error": "Username and password do not match any user in this service"}
    ]},
    {"variant_id": "NEG-002", "description": "wrong username", "iterations": [
      {"fields": [{"field_name": "username", "value": "not_a_real_user"}, {"field_name": "password", "value": "secret_sauce"}],
       "expected_error": "Username and password do not match any user in this service"}
    ]}
  ]
}

Plan (this scenario's cap allows only 1 negative test here — NEG-001 is picked as the
highest-confidence/first-listed variant; if max_negative_cases were 2, NEG-002 would render too, the
same way, as a second test in this same "tests" array):
{
  "tests": [
    {
      "name": "positive — standard user login with valid credentials succeeds",
      "type": "positive",
      "steps": [
        {"action": "navigate"},
        {"action": "enterText", "locator_key": "username_field", "value": "standard_user"},
        {"action": "enterText", "locator_key": "password_field", "value": "secret_sauce"},
        {"action": "click", "locator_key": "login_button"},
        {"action": "verifyUrl", "value": "/inventory.html", "message": "User should be redirected to the inventory page after successful login"}
      ]
    },
    {
      "name": "negative — login with a wrong password shows an authentication error",
      "type": "negative",
      "steps": [
        {"action": "navigate"},
        {"action": "enterText", "locator_key": "username_field", "value": "standard_user"},
        {"action": "enterText", "locator_key": "password_field", "value": "wrong_password"},
        {"action": "click", "locator_key": "login_button"},
        {"action": "verifyContainsText", "locator_key": "error_message", "value": "Username and password do not match any user in this service", "message": "An authentication error should be shown for a wrong password"}
      ]
    }
  ],
  "missing_actions": [],
  "missing_locators": []
}

== Example 2 — negative + boundary variants, a soft assertion ==

Scenario:
{
  "scenario_id": "M02_BS_014",
  "title": "Search for products by keyword",
  "business_objective": "Verify the product search returns matching results and handles edge-case input",
  "actor": "Logged-in user",
  "preconditions": ["User is on the inventory page"],
  "steps": [
    "User enters a keyword in the search box",
    "User presses Enter",
    "Matching products are displayed"
  ],
  "expected_result": "Only matching products are shown",
  "module_id": "M02"
}

Plan:
{
  "tests": [
    {
      "name": "positive — search for a valid product keyword returns matching results",
      "type": "positive",
      "steps": [
        {"action": "enterText", "locator_key": "search_box", "value": "Backpack"},
        {"action": "pressKey", "locator_key": "search_box", "value": "Enter"},
        {"action": "verifyVisible", "locator_key": "results_list", "message": "Results list should be visible after a valid search"}
      ]
    },
    {
      "name": "negative — search with an empty keyword shows no results message",
      "type": "negative",
      "steps": [
        {"action": "enterText", "locator_key": "search_box", "value": ""},
        {"action": "pressKey", "locator_key": "search_box", "value": "Enter"},
        {"action": "verifyVisible", "locator_key": "no_results_message", "message": "An empty search should show a no-results message, not an error"}
      ]
    },
    {
      "name": "boundary — search with a maximum-length keyword does not break the input",
      "type": "boundary",
      "steps": [
        {"action": "enterText", "locator_key": "search_box", "value": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        {"action": "verifyValue", "locator_key": "search_box", "value": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "message": "Search box should accept and retain a very long keyword without truncation", "soft": true}
      ]
    }
  ],
  "missing_actions": [],
  "missing_locators": []
}

== Example 3 — sibling/equal-weight cluster (nav bar): ONE test walks every sibling ==

When several locators share the same "cluster" and are independent siblings (no one depends on another
having run first — e.g. a row of nav links), do NOT write a separate test per locator and do NOT
collapse them into checking just one. Write ONE positive test that visits each in turn.

Scenario:
{
  "scenario_id": "M01_BS_020",
  "title": "Navigate using the top navigation bar",
  "business_objective": "Every top-level navigation link reaches its own destination page",
  "actor": "Guest user",
  "steps": ["User clicks each navigation bar link in turn and reaches the expected page"],
  "expected_result": "Every navigation link reaches its own destination",
  "module_id": "M01"
}

(the locator list above showed 4 locator_keys all sharing "cluster": "navigation" —
resources_link, about_link, subscriptions_link, for_business_link)

Plan:
{
  "tests": [
    {
      "name": "positive — navigation bar links all reach their expected pages",
      "type": "positive",
      "steps": [
        {"action": "navigate"},
        {"action": "click", "locator_key": "resources_link"},
        {"action": "verifyUrl", "value": "/resources", "message": "Resources link should reach the Resources page"},
        {"action": "goBack"},
        {"action": "click", "locator_key": "about_link"},
        {"action": "verifyUrl", "value": "/about", "message": "About link should reach the About page"},
        {"action": "goBack"},
        {"action": "click", "locator_key": "subscriptions_link"},
        {"action": "verifyUrl", "value": "/subscriptions", "message": "Subscriptions link should reach the Subscriptions page"},
        {"action": "goBack"},
        {"action": "click", "locator_key": "for_business_link"},
        {"action": "verifyUrl", "value": "/business", "message": "For Business link should reach the Business page"}
      ]
    }
  ],
  "missing_actions": [],
  "missing_locators": []
}

== Example 4 — prompt/chat submit-and-verify-response ==

For an AI-assistant/chat-style input (not a traditional form): enter the prompt, submit it, then
verify a response actually appeared — never stop after just navigating or just filling the input.

Scenario:
{
  "scenario_id": "M01_BS_005",
  "title": "Submit prompt using Enter key",
  "business_objective": "A user can submit a prompt with the Enter key and receive a response",
  "actor": "User",
  "steps": ["User types a prompt into the input box", "User presses Enter", "A response is displayed"],
  "expected_result": "The AI response appears after submission",
  "module_id": "M01"
}

Plan:
{
  "tests": [
    {
      "name": "positive — submitting a prompt with Enter displays a response",
      "type": "positive",
      "steps": [
        {"action": "navigate"},
        {"action": "enterText", "locator_key": "prompt_input", "value": "What is the capital of Australia?"},
        {"action": "pressKey", "locator_key": "prompt_input", "value": "Enter"},
        {"action": "verifyVisible", "locator_key": "response_container", "message": "A response should appear after submitting the prompt"}
      ]
    }
  ],
  "missing_actions": [],
  "missing_locators": []
}

== Test counts ==
- This scenario touches $distinct_cluster_count distinct functional area(s) (see "cluster" in the
  locator list above). Write ONE positive test per distinct cluster that has locators offered above —
  each covering that area's own realistic flow end-to-end. If everything belongs to one cluster (or no
  cluster labels are present), write exactly 1 positive test as before.
- Two different shapes for "cover a cluster," depending on what the locators in it actually are:
  - **Dependent sequence** (Example 1's login shape) — the cluster's locators form one ordered form/
    flow where each step depends on the ones before it (fill username, THEN fill password, THEN
    click submit). One positive test expresses the whole sequence end-to-end.
  - **Independent siblings** (Example 3's nav-bar shape) — the cluster's locators are 3+ parallel,
    equally-weighted options with no dependency between them (nav links, filter buttons, tab labels).
    Still ONE positive test, but it visits each sibling in turn (click → verify → go back → next
    sibling) rather than treating only one of them as "the" test.
  Use the scenario's own wording and the locators' "action"/"expected_result" fields to judge which
  shape fits — a scenario about "clicking through navigation options" is Example 3's shape even if it
  only lists one cluster; a scenario about "logging in" or "submitting a form" is Example 1's shape.
- At most $max_negative_cases negative test(s), TOTAL for this scenario (not per cluster) — this cap is
  final, never exceed it regardless of how many clusters/intents exist. When choosing which case to
  cover, prefer the highest-"confidence" cluster/locator, and only pick an intent that actually has a
  negative_variant with a real expected_error in the Test Data above (see the verification contract
  below) — never invent one for an intent with no negative data.
- At most $max_boundary_cases boundary test(s), TOTAL for this scenario — same final-cap and
  real-test-data-only rule as negative tests above.

== Verification contract — what makes a test actually pass/fail correctly ==

- Positive click/navigate: assert the DESTINATION state — verifyUrl and/or verifyVisible/
  verifyContainsText on content that only appears AFTER a successful click/navigation. Never just
  "the click didn't throw."
- Positive fill+submit: assert the resulting success indicator (confirmation message, redirect URL,
  updated count/state) — use the intent's expected_result and/or the Test Data's positive_dataset.
- Negative (bad/boundary data submitted): assert that the MATCHING positive test's success indicator
  does NOT appear (still on the same URL, success banner hidden/absent), OR — if the Test Data has an
  explicit expected_error for that variant — assert that error indicator DOES appear. Ground the
  assertion in something from the Test Data or the scenario, never a bare invented string.
- No genuine negative pathway exists for an intent (e.g. a plain nav-menu click with no invalid-input
  variant in the Test Data): DO NOT write a negative test for it at all — leave that slot unused rather
  than asserting a fabricated placeholder value (e.g. asserting a heading equals "" with no basis).

== Lessons learned / known pitfalls (from real generated-script failures) ==

- **Don't assert an exact URL/title when a redirect or branding prefix is plausible.** A real app
  redirected "/" to "/app" after sign-in, and rendered its <title> as "Google Gemini" instead of the
  scenario's own "Gemini" — exact verifyUrl/verifyTitle chased a moving target that was never the
  meaningful assertion. If the scenario/expected_result doesn't state an exact literal, use
  verifyUrlContains/verifyTitleContains instead of verifyUrl/verifyTitle.
- **A button/link/icon-only control is never a fill target.** If the only locator that seems to match
  "the input field" in this scenario is described as (or its key/description reads like) a button, icon,
  menu, or link — e.g. "microphone", "menu", "sparkle" — it is NOT the text input, even if it's the
  closest-sounding name offered. Add the real input to "missing_locators" instead of filling the wrong
  element; a plan-validation guard drops any enterText/clearAndEnterText step aimed at a role="button"/
  "link"/etc. locator, so writing one wastes the step for nothing.
- **A link labeled "Opens in a new window" navigates a NEW tab, not the current page.** Do not write
  verifyUrl/verifyContainsText expecting the CURRENT page to change after clicking one — assert the click
  itself succeeded (or skip further assertion on that link) and continue the rest of the test against the
  original page, exactly as it was before the click.
- **Never invent an upload file name.** Only use a file path/name that literally appears in the Test Data
  above for this scenario's uploadFile step. If Test Data has none, add it to "missing_locators"/
  "missing_actions" rather than making one up — a fabricated filename fails with a file-not-found error
  that looks like a locator bug but isn't one.

== Rules ==

1. NEVER invent an action, locator_key, or flow name that is not in the lists above. If a step in the
   scenario genuinely needs one that doesn't exist, do NOT guess or approximate with something similar —
   omit that step/test entirely and instead add a short plain-English description of what's missing to
   "missing_actions" (for a verb the action library doesn't have) or "missing_locators" (for an element
   with no matching locator_key) at the top level. It is always better to under-generate than to invent.
2. Use "useFlow" ONLY when "Allowed reusable flows" above actually lists a matching entry for this
   project — most projects have none, so most of the time you should write the explicit step sequence
   yourself (Example 1's shape), not wait for or assume a flow exists. When a matching flow genuinely
   is listed, prefer it over hand-writing the same steps.
3. Data iterations: if a test-data variant provides multiple "iterations" (up to $max_data_iterations),
   this plan format does not support in-test loops — pick the single most representative iteration value
   for that variant rather than trying to express a loop.
4. Test names must clearly describe what is being tested, in the same style as the examples above.

Return ONLY the JSON object described above. No markdown fences, no explanation, no extra text before or after it.
""")


# ── Locator merge reconciliation (build_named_locator_map's ambiguous remainder) ──
#
# Used only when a dom_elements.json rescan has both unmatched new elements
# AND existing locator_map.json entries whose source element no longer
# appears — the deterministic id-match and content-match fast paths in
# build_named_locator_map already resolved everything else. Never runs on
# every element, only this leftover, ambiguous set.

LOCATOR_RECONCILE_PROMPT = Template("""
A DOM rescan found elements that don't deterministically match the existing
locator map. For EACH "new element" below, decide whether it is the SAME
logical control as one of the "removed candidates" (just relocated to a new
locator — e.g. the app added a wrapper div, changed an id, or reordered
attributes) or a GENUINELY NEW element with no prior counterpart.

== New elements (not matched by id or by identical locator) ==
$new_elements_json

== Removed candidates (existing locator_map.json entries whose source element
   no longer appears in this scan) ==
$removed_candidates_json

Return ONLY a raw JSON object (no markdown fences, no explanation) mapping
each new element's "locator_id" to the "_key" of the removed candidate it
replaces — include an entry ONLY when you are confident it's the same
logical control, and OMIT a new element entirely if it's genuinely new (do
not guess; a missed match just means a new key gets minted, which is safe —
a wrong match would silently point an existing key at the wrong element).

{
  "LOC-0042": "search_box",
  "LOC-0057": "login_button"
}
""")
