# PassFailAgent

The **Pass/Fail Engine** of the evaluation workflow. It turns Output Validation's deterministic checks and grounded judgements into one
verdict per test and a runtime verdict per BRD acceptance criterion. It separates what the app got wrong from what MTA could not do.
It makes no LLM calls; the logic is in `engines/verdict/passfail.py`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `output_validation` | object | yes | OutputValidationAgent results; the step is skipped without them |
| `evidence_collection` | object | no | Bundles: errors, duration and observed output, used for the actual-output summary |
| `requirements` | list | no | Criterion statements and `oracle_hint` |
| `on_test_update` | callable | no | Pipeline hook that updates each TestCase row |

## Output
- `pass_fail`:
  - `counts`;
  - `pass_rate` (passed ÷ (passed + failed));
  - `tests[]`: verdict, score, strength, decided_by, reasons, supporting_issues, actual_output;
  - `criteria[]`: runtime_verdict, strength, the test counts, and `mixed` (whether both passing and failing tests exist).
- `execution_results`: the legacy live-execution shape (`id, code, status, judge_score, judge_reasoning, duration_ms, actual_output,
  strength, decided_by`). Requirement traceability turns it into runtime evidence, and compliance scoring counts it. Both work unchanged.
- `live_reachable` / `live_status = connected` when at least one test executed (used by the scoring gates).

## Test verdict rules (in order)
1. **Not validatable → `not_executed`.** Blocked, not mappable, or out of time. The reason is kept.
   - **Input rejected → `inconclusive`.** A positive test that produced nothing, where the app's own validation rejected the input
     ("Please add…", "X is required", "cannot be empty", "at least one … before"). MTA's test data was incomplete; this is not an
     app defect.
2. **The flow stopped early.**
   - Login or session problem → `inconclusive` ("test setup problem, not an app defect").
   - Element not found, plan time limit or browser closed → `inconclusive` ("MTA could not drive the UI").
   - The app still working when MTA's wait limit was reached → `inconclusive`, unless the expectation states a time limit (then
     the `time_limit` check decides, and exceeding it is `failed`).
   - Any other stop, such as a download failure or a 5xx → `failed`, as an app defect.
3. **Any core deterministic check failed → `failed`, E5.** For example: no document, wrong format, no reply, non-2xx, nothing
   changed, or a time limit exceeded.
4. **Judge.**
   - `meets`, or `partially_meets` with a score of at least 70 → `passed`, E4.
   - `does_not_meet`, or `partially_meets` below 70 → `failed`, E4, with the unmet items listed.
   - `partially_meets` below 70 with no `not_met` items, only `cannot_tell` ones → `inconclusive`. Nothing contradicted the
     expectation; part of it just wasn't visible in the captured output.
   - `cannot_tell` → `inconclusive`.
5. **No judgement.**
   - Unscored flow check, or a criterion with `oracle_hint = deterministic` whose core checks all pass → `passed`, E5.
   - Otherwise → `inconclusive` ("output captured but not judged").

Supporting check failures, such as a short document, a missing input term or a JavaScript error, never flip a verdict. They are listed
as `supporting_issues` and in the TestCase reasoning.

## Criterion rollup (scored tests only)
- `refuted`: at least one failed test. The strength comes from the failing tests.
- `supported`: at least one passed test and none failed.
- `unverified`: otherwise.

The final criterion verdict, combining this with static code evidence, is made by requirement traceability (`engines/trace/decide.py`:
a runtime refutation beats everything, then runtime support, then static evidence). The BRD Compliance Engine scores it.

## Relation to `live_agent_execution`
That agent is now a fallback. When `pass_fail` exists, it only runs tests this engine left `not_executed`, and only for Chatbot,
REST API, Hybrid or Unknown apps, where its endpoint auto-detection can reach the agent. Its results are appended to these, so no test
is sent twice.
