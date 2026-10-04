# HealingAgent

Native ADK agent. Runs after `UIExecutionAgent`. The sole healing agent in this codebase — no
deterministic root-cause-table implementation lives alongside it, no composition layer, no fallback
to a prior design. Reference implementation for migrating the rest of the pipeline's agents to ADK.

## Inputs
- Playwright JSON results (from `ui_execution`, or the latest report on disk)
- `comprehension/dom_elements.json` (current DOM state, legacy specs' locator fix path)
- `test_creation/locator_map.json` (action-library specs' locator fix path — see below)
- `test_creation/test_suite.json` (per-spec `generation_mode`, to pick which locator fix path applies)
- `test_creation/test_data/test_data.json` (expected test-data values, by scenario id)
- `project.yaml`'s configured `url`
- Failing `.spec.ts` file contents

## Process

1. **`read_failure_report`** parses the Playwright JSON into structured failing-test entries, keyed
   by the spec path relative to `test_creation/test_scripts/` (preserving module subdirectories —
   this is a clean-implementation fix for the old agent's `os.path.basename()` bug, which silently
   broke module-scoped projects). A test whose Playwright status is `"flaky"` (failed its first
   attempt, passed on Playwright's own retry) is excluded here, same as `ui_execution/agent.py`'s
   pass/fail counting — it already recovered on its own; healing it would mean patching a locator
   that was never actually broken.
2. A Gemini-backed `LlmAgent`, wrapped in an ADK `LoopAgent(max_iterations=N)`, reasons over each
   failure's error message and picks a repair tool: `propose_locator_fix`, `propose_timing_fix`,
   `propose_compilation_fix`, `propose_test_data_fix`, `propose_navigation_fix`, or
   `propose_fixture_fix`. This is genuine model reasoning, not a hardcoded root-cause table.
3. **`apply_patch`** is the only tool that writes a `.spec.ts` file — structural validation (non-empty,
   balanced braces/parens, a real `test`/`test.skip`/`test.fixme` block) gates every write, then an
   atomic tmp-file + `os.replace()`. **Exception**: when `propose_locator_fix` is called on a spec whose
   `test_suite.json` entry has `generation_mode: "action_library"` (ScriptGenerationAgent's plan-based
   pipeline), there is no raw Playwright locator call to extract from the spec text — only
   `action.<verb>('locator_key', ...)` calls. That variant extracts the `locator_key`, live-checks it,
   and — if broken — repairs `test_creation/locator_map.json`'s entry directly via
   `repair_named_locator()` and returns `"applied": true`. No `apply_patch` call happens for that
   result: fixing the one shared `locator_map.json` entry fixes every spec referencing the key, so the
   model goes straight to `run_tests`. Legacy specs (no `generation_mode`, or any other value) are
   completely unaffected — `propose_locator_fix` and `apply_patch` behave exactly as before.
4. **`run_tests`** re-executes just the patched spec file(s) via `UIExecutionAgent` to verify. The
   loop ends (via `tool_context.actions.escalate`) once no failing tests remain.
5. **`mark_not_healable`** is called instead of patching when a failure is judged a real
   application/environment/JS/auth defect — rewriting a test's expectations to match broken behavior
   is a worse failure mode than leaving it red. Also ends the loop once nothing remains.
6. `max_iterations` reached with failures still outstanding → loop stops naturally, `status: "partial"`.

## Known pitfalls — two real failure classes this agent now diagnoses correctly

Both found on a real project's actual failing run, where the generic root-cause bucket
(`propose_locator_fix`) would otherwise have misdiagnosed them or missed them entirely:

- **Ambiguous (not missing) locators.** A `role`-typed locator matching 2+ elements (e.g. two "Sign
  in" buttons — one text, one icon, shown responsively) is a Playwright strict-mode violation at
  actual runtime, exactly as broken as one matching 0. The live re-check both `propose_locator_fix`
  (action-library path) and its legacy-spec counterpart use now requires `count() == 1`, not just
  `count() > 0` — a multi-match locator no longer silently reports "this key is fine, the failure is
  something else."
- **Missing upload-fixture files.** `ActionEngine.uploadFile()`'s error (`ENOENT` from the runtime, or
  the clearer "Upload fixture not found" message a current build throws) is tagged
  `[locator_key=...]` exactly like every other `ActionEngine` failure — nothing about the error text
  alone distinguishes it from a real locator bug. `propose_fixture_fix` recognizes this signature and
  routes straight to `mark_not_healable`: no tool here can create a fixture file, so treating it as a
  locator problem just wastes a live-browser re-check confirming a locator that was never broken.

## Structural safety boundary

No tool in `tools.py` can write `business_scenarios.json`, acceptance criteria, assertion expected
values, `intents.yaml`/`dom_intents.json`, or any `workflows/*.yaml` — enforced structurally (the tool
surface has no path to those files), not by instruction text alone.

## Outputs

```json
{
  "module": "healing",
  "status": "success" | "partial" | "failed",
  "specs_healed": N,
  "tests_healed": N,
  "not_healable": [{ "spec_file": "...", "test_name": "...", "reason": "..." }]
}
```

`status` is `"partial"` (never `"failed"`) whenever attempts are exhausted but real failures remain —
`"failed"` is reserved for genuine infra errors: no report found, or `GOOGLE_API_KEY`/ADK unavailable.

Also updates `test_creation/test_suite.json` → `status: "healed"` on every spec with at least one
patched block.

## Failure behaviour

No CSS-based or other deterministic fallback exists for this agent. If Gemini/ADK is genuinely
unavailable (missing `GOOGLE_API_KEY`, ADK import/runtime error), `execute()` returns
`status: "failed"` with a clear error rather than silently degrading to a weaker healing strategy.
