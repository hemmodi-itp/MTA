# ScriptGenerationAgent

Produces one `.spec.ts` file per business scenario. The LLM never writes TypeScript — it returns a
validated JSON test **plan** built from a fixed action vocabulary, named locator keys, and reusable
flows; a deterministic renderer turns that plan into the actual spec file.

## Inputs
- `test_creation/scenario_element_map.json` (from SemanticMapAgent)
- `comprehension/business_scenarios.json`
- `test_creation/test_data/test_data.json`
- `comprehension/dom_elements.json` (per module, or flat for single-module projects) — via the locator map

## Outputs
- `test_creation/locator_map.json` — one flat file per project, merge-written every run
- `test_creation/pages.ts` — every module's Page-factory class + `PAGE_REGISTRY`, regenerated every run
- `test_creation/flows.generated.ts` — rebuilt from `flows.json` every run, when a `flows.json` exists
- `test_creation/test_plans.json` — the validated plan per scenario (tier 0/1 only), keyed by `scenario_id`
- `test_creation/test_scripts/{module_id}/test_{id}_{snake_title}.spec.ts` (one per scenario)
- `test_creation/test_suite.json` (updated after each run; each spec entry carries `generation_mode`)

## The plan-JSON contract

The LLM picks only from:
- **Actions** (`ALLOWED_ACTIONS` in `agent.py`, mirroring `application_assets/_shared/runtime/ActionEngine.ts`'s
  methods 1:1): `navigate, click, doubleClick, hover, enterText, clearAndEnterText, pressKey, checkCheckbox,
  uncheckCheckbox, selectDropdownByText, selectDropdownByValue, scrollIntoView, waitForElement,
  waitForTimeout, dragAndDrop, uploadFile, verifyVisible, verifyHidden, verifyText, verifyContainsText,
  verifyValue, verifyEnabled, verifyDisabled, verifyChecked, verifyCount, verifyUrl, verifyUrlContains,
  verifyTitle, verifyTitleContains, takeScreenshot, goBack, reload, verifyNoPageErrors, useFlow`.
  `verifyUrlContains`/`verifyTitleContains` exist specifically for redirects/branded-title suffixes a
  scenario doesn't pin an exact literal for (see "Known pitfalls" below) — same page-level,
  no-`locator_key` shape as `verifyUrl`/`verifyTitle`.
- **Locator keys**: this scenario's slice of `locator_map.json` (translated from `scenario_element_map.json`'s
  `locator_id`-keyed `relevant_elements` via a reverse index), excluding any key that failed the live
  validation pass (see below) — the LLM is never offered a known-dead locator. When SemanticMapAgent
  enriched a `relevant_elements` entry with `action`/`expected_result`/`cluster`/`confidence` (see its
  `agent.md`), those pass through into `allowed_locators` too (`_allowed_locator_entries_for_scenario`)
  — absent for BRD-only projects, in which case every key here is a bare `{key, description}` as before.
- **Flows**: names from `flows.json`, invoked via `{"action": "useFlow", "flow": "...", "args": {...}}`.

## Test counts — clusters scale positives, project.yaml caps stay final

- **Positive tests scale with distinct functional clusters** offered for the scenario (one per
  cluster, covering that area's own realistic flow) — not capped by `max_negative_cases`/
  `max_boundary_cases` (nothing ever capped positive-test count; previously it was just "whatever the
  LLM wrote," typically 1). This is how a scenario touching 5-7 intents across a couple of functional
  areas produces more than one positive test without touching the caps below.
- **A cluster's positive test takes one of two shapes**, per `ACTION_LIBRARY_PROMPT`'s few-shot
  examples:
  - *Dependent sequence* (Example 1 — login) — the cluster's locators form one ordered flow where
    each step depends on the ones before it. One test expresses the whole sequence end-to-end
    (`enterText` username → `enterText` password → `click` submit → verify destination).
  - *Independent siblings* (Example 3 — nav bar) — the cluster's locators are 3+ parallel,
    equally-weighted options with no dependency between them (nav links, filter buttons, tabs). Still
    one test, but it visits every sibling in turn (`click` → verify → `goBack` → next sibling) rather
    than only exercising one of them.
  A fourth example (prompt/chat submit-and-verify-response) covers AI-assistant-style inputs, which
  don't fit either the login or nav-bar shape.
- **`max_negative_cases`/`max_boundary_cases`/`max_data_iterations`** (`project.yaml`'s
  `test_generation:` block, read via `tools/config/test_generation_config.py`) remain a **hard,
  final ceiling, per scenario** — 1/1 by default. These are never scaled up by cluster/intent count.
  What changes is *which* intent's data fills those fixed slots: the prompt is told to prefer the
  highest-`confidence` cluster/locator, and to only pick an intent that has a real `negative_variant`
  with an `expected_error` in Test Data — never to invent one.

## Verification contract — no fabricated negative-test assertions

| Action type | What the test must assert to actually pass/fail correctly |
|---|---|
| Positive click/navigate | The destination state changed — `verifyUrl`/`verifyVisible`/`verifyContainsText` on content that only appears *after* success. Not "the click didn't throw." |
| Positive fill+submit | The resulting success indicator (confirmation, redirect, updated count) — from the intent's `expected_result` and/or Test Data's `positive_dataset`. |
| Negative (bad/boundary data) | The matching positive test's success indicator does **not** appear, or — if Test Data has an `expected_error` — that error indicator **does** appear. |
| No genuine negative pathway (e.g. a plain nav-menu click) | Skip the negative slot for that intent entirely — never fabricate a placeholder assertion. |

This is prompted as literal instruction text in `ACTION_LIBRARY_PROMPT`, and mechanically
backstopped by `_drop_placeholder_negative_tests` (`agent.py`): a `"negative"`-typed test whose *only*
assertions are a hardcoded empty-string value, with no real `expected_error` anywhere in this
scenario's Test Data, is dropped after `_validate_plan` succeeds — logged as a warning, not a hard
failure, since the rest of the plan (positive/boundary tests) is still good. This is the concrete fix
for a bug found in early generations: a plain nav-menu click (no real invalid-input pathway) got a
"negative" test asserting `verifyText(..., "", "Page heading should be empty indicating failed
load")` — a placeholder that trivially passed regardless of real app behavior.

## Discovery mode behavior (BOTH / URL ONLY / BRD ONLY)

Mirrors `agents/comprehension/discovery/agent.md`'s mode table:

| Mode | `dom_elements.json` / locators available? | Effect here |
|---|---|---|
| BOTH / URL ONLY | Yes | Full locator-backed scripts, clustering-driven positive test count when SemanticMapAgent enriched the map |
| BRD ONLY | No | No DOM scan ran, so there's nothing to build `locator_map.json`/`pages.ts` from — this step (and everything downstream that needs locators: execution, healing) should be disabled in `workflows/agents.yaml` for BRD-only projects, per `discovery/agent.md`'s note |

## `test_data.json` drift check

`_test_data_drift_warning` logs a warning (not a failure) when `test_data.json` has records but *none*
of their `scenario_id`s overlap with current `business_scenarios.json` — the exact silent-drift bug
found in one real project, where `test_data.json` still used a legacy `SC-001`-style id scheme after
`business_scenarios.json` moved to `M01_BS_001`-style ids, so every scenario generated with
`test_data = {}` even though rich test data existed on disk.

## `scenario_element_map.json` staleness check

`_scenario_element_map_coverage_warning` logs a warning listing any `business_scenarios.json`
scenario_id with **no entry at all** in `scenario_element_map.json` (as opposed to an entry with few
elements, which is a legitimately thin scenario, not a stale one). Found in a real project where
`business_scenarios.json` grew from 3 generic scenarios to 17 real ones (a later BRD/comprehension run
added 14), but `semantic_map` was never rerun — `SemanticMapAgent` maps every scenario on every run
with no incremental skip, so this only happens when the step simply wasn't re-invoked. Every missing
scenario gets zero `relevant_elements` here, so this agent has literally no locators to offer the LLM
for it — the result is a near-empty spec (often just `navigate()` alone) with no signal why, no matter
how good the few-shot examples above are. **Fix is operational, not a prompt change**: rerun
`semantic_map` (then `script_generation`) for the project.

Every `verify*` step must carry a `message`; any `verify*` step may carry `"soft": true` to collect the
failure and keep running instead of stopping immediately. Anything the scenario needs that isn't in these
lists is reported in the plan's `missing_actions`/`missing_locators` — never guessed — and flagged to
`human_review_queue.json` via `flag_missing_capability`. Four full few-shot examples are embedded in
`prompt.py`'s `ACTION_LIBRARY_PROMPT` (an explicit login sequence, a negative/boundary/soft-assertion
search flow, a sibling-cluster nav bar, and a prompt/chat submit-and-verify-response flow) to anchor the
exact shape from the first call.

## Known pitfalls — mechanically guarded, not just prompted

Each of these was a real failure class found in generated scripts, and each now has both prompt guidance
(`ACTION_LIBRARY_PROMPT`'s "Lessons learned" section) *and* a code-level guard that doesn't depend on the
LLM actually following the prompt text:

| Pitfall (real failure observed) | Prompt guidance | Code-level guard |
|---|---|---|
| `enterText` filled a role="button" element (the page's microphone button) because the real prompt textarea was never discovered as its own locator, and the button was the closest-sounding key offered | "A button/link/icon-only control is never a fill target" | `_flag_action_locator_type_mismatches` drops any `enterText`/`clearAndEnterText` step whose `locator_key` resolves to a role-typed `button`/`link`/`checkbox`/etc. locator, after `_validate_plan` and `_drop_placeholder_negative_tests` |
| `verifyUrl("/")`/`verifyTitle("Gemini")` failed because the real app redirects to `/app` and renders "Google Gemini" | Prefer `verifyUrlContains`/`verifyTitleContains` when the scenario doesn't pin an exact literal | N/A — this one is prompt-only; the app's real observed behavior can't be validated at generation time without a live page, unlike the locator-type case above |
| A `role`-typed locator matched 2 elements (e.g. two "Sign in" buttons, one text one icon, shown responsively) — a Playwright strict-mode violation at runtime that the old live-validation check missed | — | `_locator_entry_resolves`'s live dry-run now requires `count() == 1`, not just `count() > 0` — a locator matching 2+ elements is excluded from `allowed_locators` exactly like one matching 0 |
| A `target="_blank"` link ("Opens in a new window") asserted same-page content changed after clicking it — the new tab leaves the original page untouched | "Do not assert the CURRENT page changed after clicking a new-tab link" | N/A — this one is prompt-only; see `ActionEngine.click()` in the shared runtime for the matching new-tab-popup handling on the execution side |
| An `uploadFile` step referenced a filename (`sample_document.pdf`) that was never actually created on disk, failing with `ENOENT` | "Never invent an upload file name — only use one literally present in Test Data" | N/A — no fixtures directory exists to validate against at generation time; `ActionEngine.uploadFile()` now throws an actionable "fixture not found" error instead of a raw ENOENT stack, and HealingAgent's `propose_fixture_fix` classifies this as not-healable rather than misdiagnosing it as a locator bug |

`spec_renderer.py` (`tools/test_creation/script_generator/`) is the deterministic, non-LLM step that turns
a validated plan into `.spec.ts` — it also appends a `@smoke` (positive) / `@regression` (negative,
boundary) tag to each test name, so tagging can't be hallucinated.

## Where locators live

- `comprehension/dom_elements.json` (per module, or flat) — the raw discovery snapshot, unchanged and
  untouched by this agent.
- `test_creation/locator_map.json` — one flat, project-wide file this agent merges from every module's
  `dom_elements.json` (`build_named_locator_map`, in
  `tools/test_creation/script_generator/build_dom_locator_map.py`). **This is the one place a locator gets
  fixed.** The merge never deletes an existing key and never mints two keys for the same resolved locator:
  - An element whose stable `locator_id` matches an existing entry's `_source_locator_id` updates that
    entry in place (or is left untouched if nothing changed).
  - An unmatched element whose resolved locator is byte-identical to an existing entry's is treated as
    that element re-appearing under a new id, reusing the existing key.
  - Any remaining ambiguous adds/removals are handed to an LLM reconciliation call
    (`LOCATOR_RECONCILE_PROMPT`) to decide "same element, relocated" vs. "genuinely new/removed" — only
    for that leftover set, not every element.
  - An entry whose source element is confirmed gone is kept, never deleted, and flagged via
    `record_locator_drift` into `human_review_queue.json`.
- `test_creation/pages.ts` — one exported Page-factory class per module (Selenium-PageFactory style: a
  `constructor(page)` and one `Locator` getter per locator key), plus a `PAGE_REGISTRY` mapping
  `module_id → class`, all regenerated from `locator_map.json` every run
  (`write_pages_module`/`render_pages_module`). This is the actual automation surface: at test-run time,
  `application_assets/_shared/runtime/fixtures/testFixture.ts` resolves the current spec's module from its
  own file path, instantiates that module's Page class, and hands it to `ActionEngine`, which resolves
  every `locator_key` by property lookup on that Page-object instance — `LocatorManager` (the
  `{type, locator, name?} → Locator` resolver) is an internal detail only Page-class getters call, never
  `ActionEngine` or a spec directly.

## Locator validation

Once per project per run, grouped by module (one headless-browser launch per module, not per scenario):
every `locator_map.json` entry is checked against a live page. A key that fails to resolve is excluded
from `allowed_locators` for that module's scenarios and reported via `record_locator_drift` — the LLM
never sees a key already known to be dead.

## Fallback behaviour
- **NS_HTTP** → reroute to NSHTTPConnector, same plan-based prompt
- **ALT_MODEL** → claude-haiku-4-5-20251001
- **FALLBACK** → `fallback_core.fallback_generate_script()` (unchanged, raw TS) — 1 positive test +
  `test.skip` stubs; gated by `python_stub_fallback_enabled` (`workflows/agent_registry.yaml`); marks the
  spec `status: "degraded_fallback"` in `test_suite.json`. Off by default — an unfixable scenario is left
  uncovered and retried next run rather than getting a permanent stub.

## `test_suite.json` tracking

```json
{
  "spec_id": "BS-007",
  "file": "M02/test_BS-007_search_for_specific_products.spec.ts",
  "status": "new",
  "tier_used": 0,
  "fallback_route": null,
  "generation_mode": "action_library"
}
```

`tier_used`: 0 = primary LLM, 1 = NSHTTPConnector/alt model, 2 = Python fallback. `generation_mode` is
`"action_library"` for a plan-rendered spec, `null` for a tier-2 raw-TS fallback spec — HealingAgent reads
this field to decide whether a locator failure should be fixed by patching `locator_map.json`
(`repair_named_locator`) or by patching the `.spec.ts` directly (legacy path, unchanged).

## Module setup-step injection

`_inject_setup_steps` translates a module's `project.yaml` `setup` (e.g. login) into either a
`test.beforeAll` insertion (legacy/fallback-tier specs with a shared page) or a `test.beforeEach` hook
inserted right after `test.describe(...)` opens (current action-library specs, which use a per-test
`{ action }` fixture rather than a shared page) — deterministic, not LLM-prompted, so it applies
regardless of which tier produced the test bodies.
