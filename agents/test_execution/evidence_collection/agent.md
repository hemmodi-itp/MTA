# EvidenceCollectionAgent

The **Evidence Collection Engine** of the evaluation workflow. It turns the Playwright Executor's raw recordings into one evidence
bundle per test, linked to the BRD acceptance criterion the test verifies. It records facts only and makes no verdicts:
Output Validation compares the observed output with the expectation, and Pass/Fail decides. It makes no LLM calls;
the logic is in `engines/runtime/evidence.py`.

## Inputs
| Key | Type | Required | Notes |
|---|---|---|---|
| `execution_run` | object | no | PlaywrightExecutorAgent output (results with captures and observations) |
| `action_plan` | object | no | ActionGenerationAgent output: inputs sent, and unmappable or blocked tests |
| `test_cases` | list | no | Test input and expected behaviour copied into each bundle |
| `requirements` | list | no | Criterion statements copied into each bundle |
| `run_id` | string | no | Locates the run's artifact folder (`engines/runtime/paths.py`) |

The step is skipped for `brd_only`, or when nothing was planned or executed.

## Output: `evidence_collection`
```json
{"status": "collected", "counts": {"bundles": 21, "executed": 18, "with_output": 15, "documents": 12, "not_executed": 3, "criteria_covered": 14},
 "by_criterion": {"AC-01.1": ["EV-TC-001", "EV-TC-002"]},
 "manifest": "evidence_manifest.json",
 "bundles": [{
   "bundle_id": "EV-TC-001", "plan_id": "AP-TC-001", "test_id": "…", "test_code": "TC-001",
   "criterion_code": "AC-01.1", "criterion_statement": "…", "requirement_ref": "REQ-01", "kind": "brd_test", "scored": true,
   "test_input": "…", "expected_behavior": "…", "expectations": [{"expectation": "…", "pass_criteria": ["…"]}],
   "execution_status": "completed|failed|error|blocked|not_run|not_executed", "failed_step": null, "error": null,
   "inputs": [{"step": 3, "action": "fill", "field": "Problem statement", "value": "…", "synthetic": false}],
   "observed": {"ui_output": "text that appeared after the actions", "page_text_excerpt": "…", "messages": ["Documents generated successfully"],
                "reply": null, "http_response": null, "final_url": "/new",
                "documents": [{"name": "BRD.docx", "format": "docx", "readable": true, "words": 2140, "headings": ["…"],
                               "tables": 3, "text_file": "AP-TC-001/downloads/BRD.docx.txt", "text_excerpt": "…", "sha256": "…"}]},
   "artifacts": [{"type": "screenshot|failure_screenshot|page_text|page_text_before|download|document_text|http_response",
                  "path": "AP-TC-001/screenshot.png", "size": 81234, "sha256": "…"}],
   "observations": {"api_calls": 7, "api_failures": [], "slowest_call": {"path": "/api/generate", "ms": 41000},
                    "console_errors": [], "page_errors": []},
   "completeness": {"output_captured": true, "expected_output": "document", "missing": []},
   "digest": "sha256 over the bundle's artifact hashes"}]}
```

## Behaviour
1. **Identity.** Each bundle is keyed `EV-<test code>`. It carries the criterion code and statement, the requirement, the test input and the
   expected behaviour, so it can be judged on its own.
2. **Inputs.** Every fill, select, check, upload, message or HTTP body from the plan. Filler test data is flagged `synthetic`, so validators know
   which values the test chose and which were just there to complete the form.
3. **Observed output.**
   - `ui_output`: lines on the final page that were not there when it opened. It separates the result from the form around it.
   - `messages`: success, validation and error lines.
   - `reply`: the chat reply.
   - `http_response`: the HTTP response.
   - `documents`: every download opened and read. DOCX (paragraphs, heading styles, tables), PDF (text, outline, pages), XLSX (sheets,
     rows), PPTX (slide text, read from the XML directly), and md/txt/csv/json/html. An unreadable file is recorded as unreadable, with
     the error. The extracted text is saved next to the file.
4. **Integrity.** Every artifact gets a size and sha256, and each bundle a digest. `evidence_manifest.json` in the run's artifact folder lists them.
5. **Completeness.** The expected output kind comes from the plan: a document (a download step, or a positive Document Generator test), a
   chat reply, an HTTP response, or otherwise page output. Missing items are listed, for example "expected a downloaded document but none
   was produced". This is a fact for Pass/Fail, not a verdict.
6. **Not executed.** Unmappable, blocked and never-run tests get a bundle with `execution_status: not_executed` and the reason, so the
   compliance report can show what was not verified and why.

## Failure modes
File-reading errors are recorded per document and never raised. With no artifact folder (for example, a plan blocked before execution),
bundles still carry the identity and the reason; there are just no artifacts.
