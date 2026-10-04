"""prompt.py — LLM prompt template for ActionGenerationAgent.

ACTION_GENERATION_PROMPT is filled once per batch of test cases. The model sees only the elements
the Runtime Discovery Engine found on the live app (each with an id) and the BRD-traced tests; it
answers with element ids, which engines/runtime/actions.validate_steps checks against the inventory.
Login, navigation, required-field completion, waits, captures and assertions are added by the engine,
so the model only decides how each test uses the app's real inputs and controls.
"""

from string import Template

from tools.agent_eval.untrusted import UNTRUSTED_RULE

ACTION_GENERATION_PROMPT = Template("""You turn acceptance tests into browser actions on a real web application.

""" + UNTRUSTED_RULE.replace("$", "$$") + """

## The application
Type: $app_type
Testing strategy: $strategy

## Elements found on the live app (the ONLY things you may act on)
Each row has an id. kind=field (with label, type, required, options), button (text, role) or link (download).
Labels and texts were read from the app being tested.
<untrusted_content source="live_app_elements">
$inventory
</untrusted_content>

## Tests to map (each is traced to the BRD)
<untrusted_content source="tests">
$tests
</untrusted_content>

## What to return
For EACH test, one plan: {"test_code", "applicable", "reason", "steps": [{"action", "element_id", "value"}]}
- Use only element ids from the list above. Never invent ids, selectors or pages.
- Put the test's input where a user would type it: the chat box for a chat app; for a form, the field(s)
  whose label fits the content. Split the input across several fields when it clearly covers several of them
  (e.g. a project name and a problem statement). Copy wording from the test; do not add requirements.
- fill: text fields (value = the text). select: a field with options (value MUST be one of its options).
  check: checkbox/radio. upload: file field (value = short description of the file needed).
  click: a button or link. send_message: chat box (value = the message). expect_download: a download/export button or link.
- Positive tests on a form: give a value for EVERY text / textarea field of that form (required or not, every
  list or repeater input too), all describing ONE coherent, realistic scenario built from the test's input — the
  same project, product, people and numbers throughout. Many apps validate that every field has content, and a
  generator's output is only judgeable if the whole input tells one story. Put the test's own input in the fields it
  is about; derive the rest consistently from it. Leave "not applicable", "omit" and "auto-generate" checkboxes
  unchecked unless the test is about them. The engine then clicks the form's submit button and waits for the result.
  Add expect_download when the test is about the generated file. Negative / security / robustness tests: set exactly the inputs that make the test negative
  (e.g. leave a required field empty by omitting it, or enter the malicious text); then click the submit button.
- applicable=false (with a reason) only when nothing on the app can exercise the test, e.g. a pure latency or
  backend-only claim. Do not mark a test inapplicable just because it needs typing into a form.
- Return the plans in the same order as the tests, one per test_code.
""")
