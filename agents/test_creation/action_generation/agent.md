# ActionGenerationAgent

The **Action Generation Engine** of the evaluation workflow. It turns every BRD-traced test case into an executable, grounded
list of browser actions (or HTTP calls for a REST API) that the Playwright Executor runs. It sits after Runtime
Discovery and Application Classification. The logic is in `engines/runtime/actions.py`; Gemini only proposes steps.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `test_cases` | list | yes | From AgentTestGenerationAgent: `id`, `code`, `title`, `variant_type`, `input`, `expected_behavior`, `pass_criteria`, `criterion_code` |
| `runtime_profile` | object | yes | RuntimeDiscoveryAgent output: pages, forms, fields, buttons (with card/row context), downloads, chat box, login |
| `app_classification` | object | no | AppClassificationAgent output: class(es) and testing strategy |
| `live_credentials` | object | no | Only its presence is used, to decide whether a login wall blocks the plan. Credentials never enter a plan |
| `agent_profile` | object | no | `interface.endpoints` drive REST API plans |
| `mode`, `live_url` | string | yes | Skipped for `brd_only` or with no live URL |

## Output: `action_plan`
```json
{"app_type": "Document Generator", "status": "ready", "reason": null, "requires_login": true, "inventory_size": 21,
 "counts": {"tests": 20, "ready": 18, "unmappable": 2, "blocked": 0, "flow_checks": 1, "llm_mapped": 17, "ungrounded_steps_dropped": 1},
 "plans": [{"plan_id": "AP-TC-001", "test_id": "…", "test_code": "TC-001", "criterion_code": "AC-01.1", "requirement_ref": "REQ-01",
            "title": "…", "variant": "positive", "class": "Document Generator", "kind": "brd_test", "scored": true,
            "status": "ready", "source": "llm", "reason": null,
            "steps": [{"n": 1, "action": "login"},
                      {"n": 2, "action": "goto", "url": "/new"},
                      {"n": 3, "action": "fill", "target": {"id": "P0F0I1", "kind": "field", "page": "/new", "label": "Problem statement", "type": "textarea"}, "value": "…"},
                      {"n": 4, "action": "select", "target": {"…": "…"}, "value": "Executives", "synthetic": true},
                      {"n": 5, "action": "click", "target": {"kind": "button", "text": "Generate documents", "role": "submit"}},
                      {"n": 6, "action": "wait_for", "kind": "settled", "timeout_ms": 180000},
                      {"n": 7, "action": "expect_download", "target": {"kind": "button", "text": "Download DOCX", "role": "download"}},
                      {"n": 8, "action": "capture", "what": ["screenshot", "dom_text", "download"]},
                      {"n": 9, "action": "assert", "kind": "judge", "expectation": "…", "pass_criteria": ["…"]}]}]}
```
Action vocabulary: `login, goto, fill, select, check, upload, click, send_message, wait_for, expect_download, http, capture, assert`.
A target carries `label`, `name`, `type`, `text`, plus `nth` and `context` for repeated buttons (for example, which product's
"Add to cart"), so the executor can locate it with label, name, placeholder or text strategies.

## Behaviour
1. **Inventory.** Every field, button, download link and chat box from the runtime profile gets a stable id (`P{page}F{form}I{field}`,
   `P{page}B{button}`, `P{page}L{link}`). Login screens are excluded.
2. **Proposals (Gemini).** For Form, Document Generator, Workflow, Chatbot and Hybrid apps, tests are sent in batches of 12
   together with the inventory. The model answers with element ids and values, or with `applicable=false` and a reason.
3. **Grounding.** Each proposed step must name an existing element that suits the action (fill on a text field, select with
   one of the field's options, click on a button or link, send_message on the chat box). Other steps are dropped and counted in
   `ungrounded_steps_dropped`.
4. **Rules fallback.** When there is no usable proposal:
   - chat: send the test input;
   - form or Document Generator: put the input into the best-matching free-text field of the main form;
   - Dashboard: open the page and check that a chart or table is visible;
   - REST API: POST the input to the documented endpoint.

   If nothing matches, the test is `unmappable` with a reason. It is never padded into an empty plan.
5. **Completion.** Every ready plan gets:
   - `login` first, when discovery logged in;
   - `goto`;
   - synthetic data for the required fields the test left empty (skipped for negative, security and robustness tests);
   - a click on the form's submit button;
   - `wait_for` (180 s for generation);
   - `expect_download` (Document Generator, positive tests). If discovery saw no download control, which is common when
     export buttons appear only after generating, the target is `{"kind": "auto"}` and the executor finds the controls at run time;
   - `capture` and a final judged `assert` copied from the test's expected behaviour.
6. **Flow checks.** One unscored end-to-end plan per discovered form (up to 5) plus one for the chat. They prove the flow works and
   give baseline evidence. They are never counted in compliance.
7. **Blocked.** If the app is behind a login and no test account is configured, or discovery found nothing to act on, the plan
   is `blocked` with the reason and no plans are produced.

## Making submissions valid
- **One coherent scenario.** For positive form tests, Gemini fills every text and textarea field of the form, list rows included,
  from one realistic scenario built from the test's input. Apps that validate "every field" then accept the submission, and a
  generator's output can be judged against one consistent story. With 15 or more fields, tests go 3 per Gemini call.
- **List rows.** A field discovered behind a "+ Add" button (`revealed_by`) is preceded by a click on that button, once per
  button.
- **Item pages are never targets.** Elements on `/runs/<id>`-style pages belong to an earlier record, so they are left out of
  the inventory. Behaviour on a fresh result is reached by "generate first, then act" instead.
- **Label-only required fields.** A field is required when its HTML says so, or when its label does ("Name (required)", "Name *").
  Many apps only mark it in the label.
- **Demo data, only as a fallback.** Used only when a positive plan covers less than 80% of the form's text fields, for example a
  rules-only "generate then revise" plan. MTA clicks the app's own sample-data control ("Fill Demo Data", "Load sample data",
  "Autofill"…), then the test's own values overwrite it, and no generic filler is added on top. The click is `optional`: if the
  control is missing at run time, the step is skipped, not failed. Negative tests never use demo data.
- **Filler data by label:** acronyms and IDs get `MTA`, tech stack fields a stack, steps and flow fields numbered steps, scope
  fields a feature list, audience fields a role. "(required)" and "*" are stripped from generated text.
- **Generate first, then act (Document Generator).** Some tests are about behaviour that only exists after generating: export or
  download, revise or change request, preview, history and versions, generation time. When such a test is not mappable as-is, the
  plan fills the main form, generates, then acts on the result:
  - export: `expect_download` (auto);
  - revise: a `follow_up` step typed into the box that appeared after generating, then another wait;
  - history: opens the history page;
  - preview and timing: the result page is captured and timed.
  These plans are marked `source: rules`.
- **Never pressed:** sign-out and destructive controls (log out, sign out, delete account, deactivate, unsubscribe) are left out
  of the inventory.

## Failure modes
A Gemini failure for a batch is logged and that batch falls back to the rules. With no LLM connector, the rules handle everything.
With no runtime profile or no tests, the step is skipped.
