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

   **Every generated test gets a ready plan.** When Gemini says a test is not applicable and no rule maps it, or a test
   needs a failure injected (`needs_fault`), the plan is the closest action the live app offers — the class rules, else
   the chat box, the main form (the test's "Label: value" lines, else its input in the best free-text field), else the
   page whose title / headings best match the test — and carries `proxy` with the reason. A fault test runs as a
   normal, complete use of the feature (`variant: positive`). The judge is told it ran an approximation, and Pass/Fail
   never turns a proxy's shortfall into a failure. `unmappable` remains only when the app offers nothing at all
   (no element, no page, no endpoint).
5. **Completion.** Every ready plan gets:
   - `login` first, when discovery logged in;
   - `goto`;
   - synthetic data for the fields the test left empty (see "Making submissions valid"; skipped for negative, security
     and robustness tests);
   - a click on the form's submit button;
   - `wait_for` (180 s for generation);
   - `expect_download` (Document Generator, positive tests). If discovery saw no download control, which is common when
     export buttons appear only after generating, the target is `{"kind": "auto"}` and the executor finds the controls at run time.
     It is required only when the test is about the file (export, download, a format: `about_file`); otherwise it is
     `optional` ("collect the generated files") and its absence is not a failure. It always runs on the result itself,
     before any step that navigates away from it (e.g. to History);
   - `capture` and a final judged `assert` copied from the test's expected behaviour.
6. **Flow checks.** One unscored end-to-end plan per discovered form (up to 5) plus one for the chat. They prove the flow works and
   give baseline evidence. They are never counted in compliance.
7. **Blocked.** If the app is behind a login and no test account is configured, or discovery found nothing to act on, the plan
   is `blocked` with the reason and no plans are produced.

## Making submissions valid
- **One coherent scenario.** For positive form tests, Gemini fills every text and textarea field of the form, and the rows
  of every required list, from one realistic scenario built from the test's input, keeping each value short (< ~150
  characters: long inputs push a generator past its own time limit). Apps that validate "every field" then accept the submission, and a
  generator's output can be judged against one consistent story. With 15 or more fields, tests go 3 per Gemini call.
- **List rows.** A field discovered behind a "+ Add" button (`revealed_by`) is preceded by a click on that button, once per
  button.
- **Item pages are never targets.** Elements on `/runs/<id>`-style pages belong to an earlier record, so they are left out of
  the inventory. Behaviour on a fresh result is reached by "generate first, then act" instead.
- **Label-only required fields.** A field is required when its HTML says so, or when its label does ("Name (required)", "Name *").
  Many apps only mark it in the label.
- **MTA's own data first; demo data only as a last resort.** A positive plan that does not describe the whole form gets MTA's
  short filler values: in the required fields, and — on a form that generates something — in every other text / select
  field too, plus the rows of required lists (discovery marks a list required from its title, "Objectives (required)").
  Generators often validate that every section has content: BRD_Agent rejected 6 of 20 tests whose plans filled only its
  7 marked fields. Optional lists ("Additional Sections") stay empty, and so do the optional fields of every other form
  (a filler value in a search filter empties the result; in a promo or referral code it is rejected). Code-like fields
  (promo, coupon, referral, OTP, card, password …) are never guessed. A field whose own "Not applicable" or "Auto-generate" box the test ticks is left to the
  app. An app that still wants more names the fields when it rejects the submit, and the executor fills exactly those. The app's own sample-data control ("Fill Demo
  Data", "Load sample data", "Autofill"…) is clicked only when MTA can fill none of the required fields itself: demo data can
  be large (BRD_Agent's demo project ran past the app's 180 s request timeout on every attempt), which turns a feature test
  into a timeout. That click is `optional`: if the control is missing at run time, the step is skipped, not failed.
  Negative tests never get filler or demo data.
- **"Label: value" input lines.** Test design writes form input as one "Label: value" line per field. Lines that name a field
  of the form fill it (a select only with a real option); "[checked] Not applicable" / "Auto-generate: checked" on a field
  ticks that field's own box (names match up to a plural "s": "Objective" ↔ "Objectives"). Inputs written with literal
  `\n` sequences are split on those too.
  Rule-based plans use these lines instead of pasting the whole input into one box.
- **An omitted field is left alone.** When a plan ticks a field's "Not applicable / omit" box, any fill of that same field is
  dropped: the app disables it, and typing into it would hang the test.
- **Negative follow-up tests generate first.** A negative test whose negative part is the follow-up (an empty change request)
  is planned as generate, then the follow-up; the generation is completed like a positive test's so it succeeds.
- **Filler data by label:** short values that all describe one small project (a web tool to submit, approve and report on
  requests): acronyms and IDs get `MTA`, tech stack fields a stack, steps and flow fields numbered steps, objectives, metrics,
  constraints, dependencies, integrations, risks, mitigations, questions, exclusions and phases a matching sentence. A list
  row with a generic label ("Name", "Description") is filled from its list's title ("System Components"). "(required)" and "*" are stripped from generated text.
- **Generate first, then act (Document Generator).** Some tests are about behaviour that only exists after generating: export or
  download, revise or change request, preview, history and versions, generation time. When such a test is not mappable as-is, the
  plan fills the main form, generates, then acts on the result. What a test is about is read from its title, expectation,
  criterion and pass criteria — not its input data, which may mention DOCX or a tech stack without the test being about them.
  - export: `expect_download` (auto), on the result page;
  - revise: a `follow_up` step with the test's own change request (its "Change Request: …" line; a small default edit when
    it names none — never the whole multi-line input), typed into the box the result offers: discovery's box on an
    earlier result page (`box_label`, e.g. "e.g. Add a risk about vendor lock-in") and its button (`submit_text`,
    "Apply Change"); then another wait;
  - history: opens the History page (preferred over a runs list, then a dashboard);
  - preview and timing: the result page is captured and timed.
  When Gemini mapped the form, these after-result steps are still added from the rules (the model never sees the result
  page). Plans built entirely by the rules are marked `source: rules`.
- **A test that needs a fault still runs.** A test whose setup needs the app's LLM / API / network to fail, a rate limit
  or a timeout, or load, runs as an ordinary use of the feature, marked `proxy` (see Rules fallback).
- **Never pressed:** sign-out and destructive controls (log out, sign out, delete account, deactivate, unsubscribe) are left out
  of the inventory.

## Failure modes
A Gemini failure for a batch (or a test its reply skipped) is retried test by test; a test still unmapped falls back to the
rules. With no LLM connector, the rules handle everything.
With no runtime profile or no tests, the step is skipped.
