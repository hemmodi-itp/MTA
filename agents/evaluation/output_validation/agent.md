# OutputValidationAgent

The **Output Validation Engine** of the evaluation workflow. For every evidence bundle from EvidenceCollectionAgent, it checks whether the
output the app actually produced matches what the test and its BRD acceptance criterion expect. Two oracles are kept apart, because the
Pass/Fail Engine weighs them differently: deterministic checks, and a grounded LLM judge. No final verdict is given here.
The logic is in `engines/validation/output.py`; the judge prompt is in `prompt.py`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `evidence_collection` | object | yes | Bundles: inputs, observed output, documents, observations, completeness |
| `app_classification` | object | no | App type, as context for the judge |
| `run_id` | string | no | Locates the artifact folder, used to read each document's full extracted text |

The step is skipped for `brd_only`, or with no bundles.

## Output: `output_validation`
```json
{"counts": {"bundles": 21, "validated": 18, "not_validatable": 3, "checks_passed": 70, "checks_failed": 9,
            "judged": 17, "meets": 11, "ungrounded_quotes": 1},
 "results": [{"bundle_id": "EV-TC-001", "test_code": "TC-001", "criterion_code": "AC-01.1", "status": "validated|not_validatable",
              "checks": [{"id": "document_produced", "name": "A document was produced and downloaded", "oracle": "deterministic",
                          "result": "pass|fail|unknown", "detail": "BRD.docx", "weight": "core|supporting"}],
              "judge": {"oracle": "semantic", "assessment": "meets|partially_meets|does_not_meet|cannot_tell", "score": 90,
                        "reasoning": "…", "ungrounded_quotes": 0,
                        "criteria_results": [{"criterion": "…", "result": "met|not_met|cannot_tell", "quote": "verbatim output text",
                                              "quote_verified": true}]},
              "core_failures": [], "supporting_failures": ["document_not_empty"], "summary": "…"}]}
```

## Deterministic checks
| id | When | Weight |
|---|---|---|
| `executed` | always | core |
| `document_produced` | a document is expected (positive tests) | core |
| `document_readable` | a document was downloaded | supporting |
| `document_not_empty` | the document has at least 50 words | supporting |
| `document_format` | the expectation names a format (Word/DOCX, PDF, Excel, PowerPoint, Markdown, CSV) | core |
| `input_reflected` | at least half the distinctive words the test entered (filler test data excluded) appear in the document | supporting |
| `reply_present`, `reply_not_error` | chat tests; `reply_not_error` looks for tracebacks, "something went wrong" and similar | core, supporting |
| `http_2xx` | API tests | core |
| `page_changed` | positive page-output tests (new or re-ordered content, or a message) | core |
| `rejected_visibly` | negative, security, robustness and out-of-scope tests: an error or validation message, or no document generated; otherwise `unknown`, left to the judge | core |
| `no_server_errors` | any API calls (5xx fails) | supporting |
| `no_page_errors` | uncaught JavaScript errors | supporting |
| `time_limit` | the expectation states a limit ("within 30 seconds", "under 500 ms"), measured on the slowest API call, else the whole test | core |

## Semantic judge
- **Batching.** Tests go to Gemini 4 at a time, 3 batches in parallel, at temperature 0, with a structured-output schema.
- **What the judge sees.** For each test: the criterion, expected behaviour, pass criteria and the inputs entered, plus the observed
  output — the reply, page output, messages, HTTP response, or up to 12k characters of each downloaded document's full extracted text.
- **Per-item results.** Each pass criterion (or 1–4 items split from the expected behaviour) is judged `met`, `not_met` or `cannot_tell`.
- **Grounding.** Every `met` must quote the output verbatim, and `ground_judgement` checks the quote against the observed text.
  - A quote that can't be found makes the item `cannot_tell`, counted in `ungrounded_quotes`.
  - A `meets` assessment with an ungrounded item drops to `partially_meets`.
  - The score is capped at what the grounded items support (met = 1, cannot_tell = 0.5, not_met = 0).
- **Negative tests.** For negative, security and robustness tests, `met` means the app refused or safely handled the input.

## Failure modes
- **A batch fails:** that batch's tests keep their deterministic checks, with `judge_error` set.
- **No LLM connector:** deterministic checks only, and the step reports `partial`.
- **Not-executed bundles:** they become `not_validatable` with the reason.
