# SemanticDedupAgent

Single-LLM-call agent that classifies newly proposed test cases as genuinely
new coverage or semantic duplicates of test cases already in the project.

## Contract

| | |
|---|---|
| Input | `existing_test_cases: list[dict]`, `proposed_test_cases: list[dict]`, `connector_mode: str` (optional) |
| Output | `{status, approved: [...], rejected: [...], approved_count, rejected_count}` |

Called by the orchestrator's `_run_dedup()` after the `artifact_generator_testcases`
step produces candidate test cases, before they're merged into `project_state`
or written to any suite. Not wired into `full_workflow.yaml`'s step list today
(no step there is named `artifact_generator_testcases`) — this agent belongs
to the earlier intents-based architecture and currently only runs when that
step is actually invoked.

## Behavior

1. If `proposed_test_cases` is empty → `status: success`, nothing approved or rejected, no LLM call.
2. If `existing_test_cases` is empty → everything proposed is approved automatically (nothing to compare against), no LLM call.
3. Otherwise, one LLM call classifies each proposed TC as `APPROVED` (new coverage) or `REJECTED` (duplicate, with `duplicate_of` and a reason).
4. Any proposed TC the LLM response doesn't explicitly approve or reject is treated as approved (safe default — never silently drop a TC due to a parsing gap).

## Failure mode

Unlike most agents in this codebase, this one does **not** use
`BaseAgent.execute_with_fallback`'s tiered routing — it has no `_run_primary`/
`_run_ns_fallback`/`_run_py_fallback` overrides. If the LLM call itself raises,
`execute()` catches it directly and returns `status: partial` with every
proposed TC treated as approved (fail-open, not fail-closed — a broken dedup
pass should never block new test coverage from landing).
