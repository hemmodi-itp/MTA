# OrchestratorAgent

The workflow driver. Unlike every other agent in this codebase, `OrchestratorAgent` is **not** a
`BaseAgent` subclass and is **not registered** in `AgentRegistry` — it's constructed directly in
`main.py` and drives the registry/workflow rather than being driven by it:

```python
orchestrator = OrchestratorAgent(settings, agents_config, registry, run_id)
result = orchestrator.run(request_payload, workflow)
```

Singular by design — there is exactly one orchestrator per run, so `agents/orchestrator/` is its one
dedicated folder directly (no further per-agent nesting, unlike the other 3 category folders which
each contain multiple agent subfolders).

## Responsibilities

1. **Load project manifest** (`project.yaml`) and merge it into the request.
2. **Module narrowing** — when `--module` is set, narrow the request/manifest to that module's URL
   and setup steps.
3. **Auth injection** — resolve `live_login` vs `storageState` auth strategy into the request.
4. **Load persistent project state** (`project_state_manager`) — existing test cases, coverage gaps,
   new-additions suite.
5. **Run each workflow step in order** (from the loaded `workflow.steps`):
   - Skip disabled steps (`agents.yaml`'s `enabled: false`).
   - Skip steps after an upstream blocking failure, unless the step is in `workflow.always_run`.
   - Skip `discovery` if content fingerprints are unchanged (unless `--force-rediscover`).
   - For `execution`: target only the `new_additions` suite unless `--suite`/`--force-execute`.
   - Dispatch via `_try_with_fallbacks` — tries the primary internal agent (via
     `registry.build(step_name)`), falls through configured fallback tiers
     (`workflows/agent_registry.yaml`: `ns_http` → NS connector dispatch, or `python_stub` → dynamic
     `importlib` import of a fallback class) if the primary tier fails or returns `status: failed`.
   - Merge each step's output into `project_state` (`_merge_step_into_state` — special-cases
     `discovery`, `artifact_generator_testcases` [runs `SemanticDedupAgent`], `script_generation`,
     `execution`/`ui_execution`).
   - Persist `project_state` after `discovery` specifically, so fingerprints survive a killed run.
6. **Build and return the final report** (`build_final_report`) plus the NS call trace.

## Fallback dispatch (`_try_with_fallbacks` / `_dispatch_fallback_tier`)

Driven entirely by `workflows/agent_registry.yaml` per step — `connector_type: internal` tries the
registered Python agent class first; `connector_type: ns_http` skips straight to an NS HTTP dispatch.
`fallback_module`/`fallback_class` strings in that YAML are resolved via `importlib.import_module` at
runtime — a path that matters exactly as much as a static import when that YAML changes.

Only enabled tiers are tried. A tier the orchestrator can't run as a whole-agent swap — `python_stub`
without `fallback_module`/`fallback_class`, or `alt_model`/`dom_synthesized` (per-call tiers the agent
applies itself via `BaseAgent.execute_with_fallback`) — is skipped with a logged warning rather than
raising. The `comprehension` step's stub tier is `ComprehensionAgentStub` (flagged empty result, no LLM).
Agents are resolved through the lazy registry (`build_default_registry(scope="legacy")` in `main.py`),
so a step's module is imported only when that step first runs.

## Failure modes

- A step raising an exception is caught, recorded in `state.errors`, and the loop continues to the
  next step (unless it's an `AgentExecutionError`, still just logged and continued).
- A step returning `status: failed` with `blocking: True` stops the entire workflow immediately.
- All exceptions are swallowed at the orchestrator level — `run()` itself never raises; the caller
  (`main.py`) always gets a result dict with a `status` field.
