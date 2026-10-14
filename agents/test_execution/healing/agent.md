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

Also updates `test_creation/test_suite.json` → `status: "healed"` on every spec whose fixed tests pass the
burn-in (Phase 6.7), `"heal_unstable"` when they do not.

## Failure behaviour

No CSS-based or other deterministic fallback exists for this agent. Phase 6.8: the primary model
(`connectors.llm`) is tried, then each connector mode in `adk.fallback` (models from `adk.models`, via LiteLLM).
When none is usable — misconfigured, not installed, or failing before the loop changed anything — `execute()`
returns `status: "skipped"` with `healing: "skipped (<reason per model>)"`, never a pipeline failure. A loop that
fails after it started changing things still returns `status: "failed"` with the progress it made.

## Phase 0 notes

- `test_data.json` is read through `contracts.artifacts.load_records` (v1 or v2);
  `test_suite.json` status stamps are written as schema_version 2 documents.
- Token usage of the ADK loop is recorded (best effort, from event `usage_metadata`) by
  `connectors/llm/usage.py` for the benchmark's cost metric.
- Known gaps recorded in `docs/audit/current_state.md` (not changed in Phase 0):
  `apply_patch` does not restrict assertion values inside a block; `repair_named_locator`
  heals are not counted in `tests_healed`.

## Traceability guard (Phase 1)

A traced test's `test(` line carries a `{ tag: [...], annotation: [...] }` object linking it to its acceptance
criteria and test-case id. `apply_patch` rejects a new block whose header does not carry the **identical**
object (whitespace-normalised) — the patch may change the body or turn the test into `test.skip(...)`, never the
link. The rejection message quotes the object to keep; the supervisor prompt says the same. Specs without a
details object (generated before Phase 1, or with `requirements.enabled` off) are unaffected. This only adds a
guard; the existing tool-surface boundary is unchanged.

## Shared locator resolver (Phase 2)

`_locator_entry_resolves` delegates to `tools/test_creation/script_generator/locator_resolve.py` instead of a
private copy of ScriptGenerationAgent's logic (a tools/ module, not a cross-agent import). Same `count() == 1` rule
and fail-open behaviour; entries may now carry `frame` / `scope` (deep-discovery locators) and are resolved through
them. No tool gained a new write path — the tool-surface boundary is unchanged.

## Test-id attribute (Phase 4)

The live locator checks (`_live_locator_resolves`, the action-library key check, the timing probe) resolve
`getByTestId` / `testid` entries with the project's `execution.test_id_attribute`, matching the TS runtime. The
tool surface and the `count() == 1` rule are unchanged.

## Steps, sleeps and flaky re-runs (Phase 4, session 2)

- Block extraction, the details-object guard and structural validation work on `test.step`-wrapped tests.
- `apply_patch` rejects a new block that adds a fixed sleep (`waitForTimeout(` / `setTimeout(`); one the block already
  had may stay. `propose_timing_fix` returns `suggested_fix` — a web-first wait for the located element — and a
  `forbidden` note; it never suggests a sleep.
- `run_tests`: a test that passes only on a retry (`flaky`) stays open ("flaky after the patch — not counted as healed").
- `read_failure_report` still excludes Playwright-flaky tests (they recovered on their own).

## Safe healing (Phase 6)

- **Triage first** (`project.yaml healing.triage`, default on when a `healing:` section exists): the workflow's
  `triage` step (TriageAgent) writes `reports/triage.json`; this agent reuses it when it was written for the same
  report, else runs the same triage itself. Only `test_defect.locator` / `test_defect.data` failures reach the loop;
  `product_defect`, `environment`, `flaky`, `known_issue` and `unknown` are never patched.
- **Modes** (`healing.mode`): `auto` applies, `propose` (default) writes diffs to
  `test_creation/healing_proposals/<run>/`, `off` = triage only (a bare `mode: off` in YAML is read as off).
- **Locator identity (6.3)**: a broken locator_map key is repaired only when the replacement points at the SAME
  element — fingerprint (role, accessible name, tag, label, landmark container, position) of the original
  (`_fingerprint`, recorded by ScriptGeneration's live validation or `python -m tools.healing.identity capture
  --project X`; else the DOM-scan element; else the entry itself) vs. the candidate, score >= 0.75, a clear margin
  over the runner-up, and a similar accessible name. Two strategies: the DOM re-scan repair (on a scratch copy),
  then a live search of the page. Anything else is refused and listed under `needs_review`.
- **Blast radius (6.5)**: `run_tests` also re-runs every spec that uses a repaired key (directly or through a flow);
  a fix that makes a previously passing test fail is reverted and the failure marked not healable.
- **Burn-in (6.7)**: every test this run fixed is re-run `--repeat-each=3`; only specs whose fixed tests pass every
  time get `status: "healed"`.
- **Audit (6.9)**: every decision (applied, proposed, refused, reverted, verified, burn_in_failed) is appended to
  `test_execution/reports/healing_audit.jsonl` with before/after, evidence, confidence and approver.
- The validation page signs in with the module's `setup` steps and opens the entry's own `_page_url`.
- Result adds: `triage`, `mode`, `model`, `burn_in {stable, unstable}`, `reverted`, `needs_review`, `audit_log`.
