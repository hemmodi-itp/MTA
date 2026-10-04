# ExecutionAgent

Thin wrapper around `UIExecutionAgent` — runs it, then extracts per-test failures into a shape
`HealingAgent` can act on.

## Inputs
Forwards the request as-is to `UIExecutionAgent` (see its own `agent.md`).

## Outputs

```json
{
  "module": "execution",
  "status": "success|failed",
  "summary": { "suite": "...", "scenarios_executed": N, "passed": N, "failed": N },
  "results": [ ... ]
}
```

`status` reflects whether the runner itself started successfully (an infrastructure failure), not
individual test pass/fail — test outcomes live in `results`/`summary`.

## Behavior

1. Run `UIExecutionAgent.execute()`.
2. Extract failures (`_extract_failures`) — one synthesized failure entry per error message on each
   non-`success` test result (`UIExecutionAgent`'s results are a flat list — no nested
   `result.steps[]` — so failures are derived directly from each result's `errors` list).
3. Classify each failure's likely cause (`_classify_error`) into one of: `strict_mode_violation`,
   `locator_resolved_multiple_elements`, `timeout_waiting_for_element`, `locator_not_visible`,
   `locator_not_enabled`, or `element_not_found` (default).
4. Forward `failures`/`execution_id`/`suite_name` into `request` so a subsequent `HealingAgent` step
   can use them.

Not referenced by any current `workflows/*.yaml` — every standalone execution workflow
(`test_execution_only.yaml`, `execution_and_healing.yaml`) and `full_workflow.yaml` all call
`UIExecutionAgent` directly under the step name `ui_execution`, bypassing this wrapper. Kept
registered (`agents/registry_setup.py`) as a documented, currently-unwired alternate entrypoint.

## Failure mode

No tiered fallback — a `UIExecutionAgent` exception is caught directly and reported as
`status: failed`.
