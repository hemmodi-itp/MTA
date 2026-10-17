# PlaywrightExecutorAgent

The **Playwright Executor** of the evaluation workflow. It runs the plans from ActionGenerationAgent in a real Chromium
browser and records what happened, step by step, with evidence. It makes no LLM calls and decides no verdicts: the
judged expectations go on, unevaluated, to Output Validation and Pass/Fail. The logic is in `engines/runtime/executor.py`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `action_plan` | object | yes | ActionGenerationAgent output; only `ready` plans run, and a `blocked` plan skips the step |
| `live_url` | string | yes | Base URL; plan paths are resolved against it. Skipped for `brd_only` |
| `live_credentials` | object | when plans log in | Used for one login only, never written to results, logs or artifacts |
| `run_id` | string | no | Names the artifact folder |

Settings (optional, `execution.playwright` in `workflows/settings.yaml`):
- `workers` (default 3) — parallel browsers;
- `plan_timeout_s` (default 900; a revise test generates twice);
- `budget_s` (default 3600, or 5400 when plans run one at a time) — overall time limit.

## Output: `execution_run`
```json
{"status": "completed|partial|blocked|skipped", "reason": null, "duration_s": 35.0,
 "login": {"attempted": true, "succeeded": true, "landed_on": "/new"},
 "counts": {"plans": 3, "completed": 3, "failed": 0, "error": 0, "blocked": 0, "not_run": 0, "downloads": 1},
 "results": [{"plan_id": "AP-TC-001", "test_id": "…", "test_code": "TC-001", "criterion_code": "AC-01.1", "kind": "brd_test", "scored": true,
              "status": "completed|failed|error|blocked|not_run", "failed_step": null, "error": null, "duration_ms": 8200, "final_url": "/new",
              "steps": [{"n": 3, "action": "fill", "status": "passed|failed|skipped|deferred", "duration_ms": 47, "locator": "discovery-match", "detail": "…"}],
              "captures": {"screenshot": "AP-TC-001/screenshot.png", "dom_text": "AP-TC-001/dom.txt", "dom_excerpt": "…",
                           "reply": "…", "downloads": [{"file": "AP-TC-001/downloads/brd.docx", "name": "brd.docx", "size": 18234, "sha256": "…", "kind": "docx"}],
                           "response": null},
              "observations": {"network": [{"method": "POST", "path": "/api/generate", "status": 200, "ms": 41000}],
                               "console_errors": [], "page_errors": [], "http_errors": 0},
              "expectations": [{"expectation": "…", "pass_criteria": ["…"]}]}]}
```
Artifact paths are relative to `<AQP_ARTIFACT_DIR or <repo>/.aqp_artifacts>/runs/<run_id>/`. That folder is gitignored, kept after the
run (unlike the workspace), and served to the run's viewers by `GET /api/runs/:runId/execution-files/<path>`.

## Behaviour
1. **Login once.** If any plan logs in, log in with the test account and share the session with every plan, so each plan starts
   logged in, in a fresh, isolated browser context. A failed login marks every plan `blocked`, with the reason.
2. **Parallel, except for document generators.** Up to 3 browsers, one plan at a time each. A Document Generator runs one plan at a
   time, with a 90-minute budget: parallel generations on one container slow each other down and would distort timing
   requirements. Steps marked `optional` are skipped, not failed, when their element is missing. Elements are located for up
   to 20 s. Generation waits are up to 300 s. BRD tests run first and unscored flow checks last. A plan has a time
   limit, and plans that never start inside the overall budget are reported as `not_run`.
3. **Targets.** Fields and buttons are found in the page with the same label, name, card-context and position rules discovery used to
   describe them, so the executor clicks the element discovery saw. Playwright label, placeholder and role locators are the fallback.
   Checkboxes that share one label across fields (a "Not applicable" or "Auto-generate" box per field) carry a `group`, the title
   of the field they belong to. They are matched by that group only, never by label alone, so a test never ticks another field's box.
   Locating retries for 10 s, or 30 s for download buttons that appear after generation.
4. **Actions.**
   - `goto`: re-logs in if the session expired. A 4xx that still renders the page (a single-page-app deep link) is not an error.
   - `fill`, `select` (native, falling back to custom dropdowns), `check`, `upload` (built-in txt, pdf, csv, json or png
     fixtures, matched to the field's `accept`), `click`.
   - `send_message`: the reply is the text that appeared after sending.
   - `wait_for`: no loading indicator, page text stable for 3 s, and requests finished. A short status line counts as busy
     too, for example "Generating your documents — this usually takes 30–90 seconds…", "Please wait", "Processing…". Longer
     generated content that merely mentions "processing" does not.
   - `follow_up`: after generating, types the step's value into the box the result offers: the one discovery saw on an
     earlier result (`box_label`), else one labelled like a change request (change, revise, feedback, request…), else —
     only once the app has moved on from the input form — a box that is not one of the form's own fields (compared by
     the label discovery would give it). It presses the result's own button (`submit_text`, e.g. "Apply Change"), else
     the nearby revise/apply/submit button, and waits again. With no result to act on (the submit was rejected or failed)
     it fails with the app's message instead of typing into the input form.
   - `expect_download`: saves the file, with size, sha256 and type; an empty file fails. With an `auto` target:
     - **Tabbed results** (`role=tab`, `data-tab`, or tab-style button classes; 2–12 tabs, such as BRD / TSD / Flowchart): MTA
       opens every tab, saves its text and a screenshot as a result view, and uses that tab's download/export control.
     - **Otherwise** it waits up to 30 s for download/export controls and clicks up to 4, including menu items.
     - **Print buttons are never clicked.**
     - If nothing downloads but result views were captured, the step passes (the views are the evidence). Otherwise it fails.
   - `http`, `capture`.
   - `assert`: `judge` assertions are deferred; `visible` (chart or table) is checked here.
5. **Failure.** At the first failing step the remaining actions are skipped, but captures still run and a failure screenshot is taken,
   so a broken flow still leaves evidence. The step's error ends with the error the app displayed, if any (an alert, toast or
   error banner, e.g. `— the app showed: "Request failed (500)"`), so the report names the cause, not only the symptom.
6. **Incomplete input.** When a positive test's submit is rejected by the app's own validation and the message names the
   fields it wants ("Please add at least one point to every field …: Constraints."), MTA fills those fields' empty boxes with
   synthetic data (first adding a list row if the list has none) and submits once more, up to 2 rounds when the app names
   further fields. Such a message may be long (BRD_Agent named 16 fields, ~600 characters): error-shaped messages up to
   2000 characters count. Only messages that appeared since the submit count — a hint already on the page ("Please fill in
   the details below") is not a rejection. A named field's block is the smallest one under that name holding a box or a
   "+ Add" button, so a same-named menu link never claims the whole form. The `wait_for` step records what was completed; the result carries it as `completed_input`.
   A field MTA cannot set (not found, not fillable) never ends the test: the step is skipped, listed in `unset_inputs`, and
   the test goes on to submit. A field the app has disabled (e.g. after its "Not applicable" box was ticked) is left as is.
   **Did the submit produce a result?** After a positive test's submit settles, if the page is still the one the submit
   happened on and shows a new rejection, or a server / network / quota error ("Request failed (500)", "Failed to fetch"),
   the `wait_for` step fails with `the app rejected the submitted input: “…”` / `the app reported an error instead of a
   result: “…”`. The plan stops there rather than acting on a result that does not exist.
7. **Outages and re-runs.** A plan that cannot reach the app (`net::ERR_…`, "Failed to fetch", gateway 502/503/504) pauses the
   run. One worker polls the live URL for up to 5 minutes while the others wait. The plan then runs again, alone. A plan
   that hit a server error (shown on the page, or a 5xx answered to one of the app's own API calls) also runs again, alone;
   before its second re-run every worker pauses 45 s so the app's backend can recover. A plan the app's AI provider
   refused for quota (`429` / `RESOURCE_EXHAUSTED`) pauses every worker for a 90 s cool-down, then runs again, alone. Each of
   these earns up to 2 re-runs (`RERUNS`); a plan MTA could not drive (element not found, a crashed browser run) earns 1. A
   re-run that never starts (budget spent, run cancelled) keeps the latest attempt's result. Each case drops the rest of
   the run to one plan at a time. The result keeps `first_attempt_error` and `attempts`, and the run reports
   `app_outages` and `retried`. If the
   app stays down, the run carries on without waiting, and those plans' verdicts are inconclusive.

## Failure modes
A browser crash in a plan marks that plan `error`; the others still run. A launch failure returns `status: partial` with no
execution run, and later steps fall back to code-only evidence.
