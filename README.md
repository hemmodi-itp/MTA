# Master Testing Agent (MTA)

> Workflow-orchestrated, LLM-driven, resilient test generation and execution engine — from BRD/live-URL to a self-healing TypeScript Playwright suite in one command.

---

## What It Does

MTA turns a product requirements document (BRD) and/or a live application URL into a fully runnable TypeScript Playwright test suite — automatically. It reads what the application is supposed to do, scans its DOM, generates test cases with real data, compiles them into `.spec.ts` files backed by a generated Page Object Model, runs them with Playwright, heals failures with a genuine LLM tool-calling loop (not a lookup table), and delivers an HTML report.

The pipeline is **modular**, **LLM-agnostic**, and **resilient**: every LLM-based agent routes failures through a shared six-route `FailureClassifier` that keeps the pipeline alive even when the LLM, rate limits, or external services are unavailable — and every agent lives in its own dedicated folder (`agent.py` + `agent.md` + `agent.json` + `prompt.py` + `skills.py` + `tools.py` + `server.py`), never sharing files with a sibling agent.

---

## Pipeline at a Glance

```
 Project Manifest (project.yaml)
         │
         ▼
 ┌─────────────────────┐
 │  1. Discovery       │  ← BRD + URL → dom_elements.json + business_scenarios.json
 └──────────┬──────────┘    (parallel DOM scan + LLM comprehension; mandatory gateway step)
            │
 ┌──────────▼──────────┐
 │  2. Test Data       │  ← scenarios → up to 10 test variant types per scenario (LLM)
 └──────────┬──────────┘
            │
 ┌──────────▼──────────┐
 │  3. Semantic Map    │  ← scenarios + DOM → scenario_element_map.json (1 LLM call)
 └──────────┬──────────┘    maps each scenario to its relevant elements + functional clusters
            │
 ┌──────────▼──────────┐
 │  4. Script Gen      │  ← element map + test_data → validated JSON action-plan → .spec.ts (LLM)
 └──────────┬──────────┘    LLM never writes TypeScript; a deterministic renderer does
            │
 ┌──────────▼──────────┐
 │  5. UI Execution    │  ← npx playwright test (headless/headed, JSON + HTML reports)
 └──────────┬──────────┘
            │
 ┌──────────▼──────────┐
 │  6. Self-Healing    │  ← Gemini ADK LoopAgent: diagnose → repair tool → re-run → verify
 └──────────┬──────────┘    block-level patch, never a whole-file rewrite
            │
 ┌──────────▼──────────┐
 │  7. Reporting       │  ← aggregates results, marks degraded/healed specs  (always runs)
 └─────────────────────┘
```

`SemanticDedupAgent` also runs inline (not a workflow step) whenever the earlier `artifact_generator`
pipeline proposes new test cases, filtering duplicates before they merge into project state. See
[Auxiliary Agents](#auxiliary-agents--wired-but-not-in-the-default-pipeline) for agents that are
registered and functional but not part of any current `workflows/*.yaml` step list.

---

## Quick Start

```bash
# Python dependencies
pip install -r requirements.txt

# Node.js dependencies (for Playwright TypeScript execution)
npm install
npx playwright install chromium

# Run a project
python main.py --project <project-name>
```

Outputs (under `application_assets/projects/<project>/`):
- TypeScript specs: `test_creation/test_scripts/{module_id}/test_{id}_*.spec.ts`
- Page Object Model: `test_creation/pages.ts`, `test_creation/locator_map.json`
- Suite manifest: `test_creation/test_suite.json`
- Playwright HTML report: `test_execution/reports/html/{timestamp}/`
- Playwright JSON report: `test_execution/reports/json/{timestamp}_results.json`
- Report index: `test_execution/reports/index.json`

---

## Project Manifest

```yaml
# application_assets/projects/myapp/project.yaml
project:
  name: myapp
  application_name: My Application
  url: https://myapp.example.com      # required for execution; enables DOM scan
  browser: chromium
  headless: true
  interactive_scan: false             # true → require a human-recorded session instead of a live scan

input:
  brd_dir: application_assets/projects/myapp/inputs/   # optional — enables LLM comprehension

test_generation:
  max_negative_cases: 1               # hard ceiling per scenario — never scaled up by cluster count
  max_boundary_cases: 1
  max_data_iterations: 1

test_execution:
  suite: myapp

ns_config:
  base_url: http://localhost:8000     # optional — per-project NeuroStack override
```

---

## Discovery Modes

`DiscoveryAgent` (`agents/comprehension/discovery/`) is the mandatory gateway step for every workflow — if it fails with `blocking=True`, the orchestrator stops immediately and no downstream agent runs.

| Mode | Inputs | What happens |
|------|--------|-------------|
| **BOTH** | URL + BRD | DOM scan + LLM comprehension run in parallel on plain daemon threads. If BRD comprehension fails but the DOM scan succeeded, a Python rule-based synthesizer converts DOM intents straight into `business_scenarios.json` — no LLM call, `comprehension_source: "dom_synthesized"`. |
| **URL only** | URL, no BRD | DOM scan → synthetic BRD markdown → LLM comprehension. Same no-LLM synthesizer fallback as above if the LLM call fails. |
| **BRD only** | BRD, no URL | LLM comprehension only. No DOM scan, so no locators exist — execution/healing steps should be disabled in `workflows/agents.yaml` for these projects. |
| **None** | Neither | Immediate blocking failure: `"No valid input found in project.yaml."` |

`interactive_scan: true` projects skip the live browser scan entirely — a human records the session first via `python main.py --project <name> --module <id> --record`, and DiscoveryAgent reads the recorded artifacts instead of racing a human-paced session against a pipeline timeout.

---

## Playwright DOM Scanner (`tools/playwright_scanner.py`)

The actual browser-driven discovery step behind Discovery/Locator agents, via `sync_playwright()`:

1. **Navigate** — `page.goto(url, wait_until="commit")`, then polls `document.readyState` (up to 30s) and `page.wait_for_load_state("networkidle")`.
2. **Query** — `page.query_selector_all(...)` across a fixed selector set: `input, button, select, textarea, a, [role=combobox]`.
3. **Extract per element** — 12 attributes (`id, name, role, placeholder, aria-label, aria-labelledby, data-testid, data-test, data-qa, type, value, title`), `inner_text()`, `is_visible()`, `is_enabled()`, tag name, associated `<label>` text, and a hand-built CSS-path fallback (walks `previousElementSibling`).
4. **Build & rank locators** — semantic Playwright locators in priority order (`getByRole` → `getByLabel` → `getByPlaceholder` → `getByText` → `getByTestId` → raw CSS), then **demotes any role-locator that matches 2+ elements** so the LLM/renderer is never handed a Playwright strict-mode violation.
5. **Safety ceiling** — a 600s wall-clock cap stops a genuinely hung scan (not a coverage cap — every selector is still processed otherwise), with periodic checkpoint writes so a caller-side timeout can promote partial results.
6. **Persist** — `dom_elements.json` is **merge-written** across rescans (locator IDs are stabilized by content-hash via `ArtifactRegistry`, never a bare per-scan counter), plus `dom_intents.json` via `tools/intent_generator.py`.

Also supports pre-scan `setup_steps` (login/click sequences), a `storageState`/live-login auth path, and a fully separate **interactive recording mode** (`--record`) that captures a human session instead of driving the browser itself.

---

## Resilience: Six-Route Failure Classifier

Every LLM-based agent (`ComprehensionAgent`, `TestDataAgent`, `SemanticMapAgent`, `ScriptGenerationAgent`, `SemanticDedupAgent`, `HealingAgent`) routes failures through a shared `FailureClassifier` (`agents/common/failure_classifier.py`) rather than crashing or silently producing empty output.

```
Primary LLM call
   └─ Exception raised
         └─ FailureClassifier.classify(exc, attempt)
               ├─ RETRY         → same connector, exponential backoff (max 2×, capped 30s)
               ├─ NS_HTTP       → NSHTTPConnector (NeuroStack) — same prompt, remote agent
               ├─ ALT_MODEL     → claude-haiku-4-5-20251001 (lighter model, same connector)
               ├─ FALLBACK      → agents/common/fallback_core.py (deterministic Python, no LLM)
               ├─ HUMAN_REVIEW  → log to human_review_queue.json, then use FALLBACK output
               └─ FAIL_FAST     → raise immediately; orchestrator marks step as blocking failure
```

### Routing by exception type

| Exception | Route |
|-----------|-------|
| `MissingInputError` | FAIL_FAST — required file absent, no retry makes sense |
| `LLMRateLimitError` (attempt < 2) | RETRY with backoff |
| `LLMRateLimitError` (attempt ≥ 2) | NS_HTTP |
| `LLMTimeoutError` (attempt < 1) | RETRY |
| `LLMTimeoutError` (attempt ≥ 1) | NS_HTTP |
| `LLMAuthError` | NS_HTTP (credentials won't fix themselves) |
| `LLMModelUnavailableError` | ALT_MODEL |
| `LLMResponseValidationError` / `JSONDecodeError` / `ValueError` (attempt < 2) | RETRY |
| `LLMResponseValidationError` / `JSONDecodeError` / `ValueError` (attempt ≥ 2) | FALLBACK |
| `ConnectionError` / `OSError` (attempt < 1) | RETRY |
| `ConnectionError` / `OSError` (attempt ≥ 1) | NS_HTTP |
| Unknown exception | FALLBACK |

### Python fallback core (`agents/common/fallback_core.py`)

When both LLM and NS agent fail, four deterministic Python functions produce output in the **identical format** as the LLM — downstream agents cannot tell which path ran. (HealingAgent has no Python fallback tier — see Self-Healing below.)

| Function | Produces |
|----------|----------|
| `fallback_semantic_map` | Keyword-overlap element scoring — top-5 per scenario |
| `fallback_generate_test_data` | 3 fixed variants (positive, empty-required-field, boundary-max 255 chars) |
| `fallback_generate_script` | Valid `.spec.ts` with 1 positive test (`goto` + title assertion) + `test.skip` stubs per step |
| `fallback_report` | Minimal `report_fallback.json` with pass/fail counts |

Specs that ran through the Python fallback are marked `status: "degraded_fallback"` in `test_suite.json`. For `ScriptGenerationAgent` specifically this raw-TS tier is **off by default** (`python_stub_fallback_enabled` in `workflows/agent_registry.yaml`) — an unfixable scenario is left uncovered and retried next run rather than getting a permanent low-value stub.

---

## Test Data — Variant Taxonomy

`TestDataAgent` reads `business_scenarios.json` and generates test data variants per scenario. Coverage is intentionally minimal by default (`project.yaml`'s `test_generation:` block caps how many negative/boundary variants actually get used) — the table below is the full taxonomy the prompt draws from, not a fixed count generated every run.

| Variant | Description | Example |
|---------|-------------|---------|
| `positive` | Realistic valid values for all fields | — |
| `empty` | All required fields blank | `""` |
| `whitespace` | Spaces/tabs only | `"   "` |
| `special_chars` | XSS / HTML injection | `<script>alert("xss")</script>` |
| `sql_injection` | SQL injection strings | `' OR '1'='1` |
| `wrong_format` | Wrong data type | `notanemail` in an email field |
| `too_long` | MAX_LENGTH + 1 chars | `"a" * 256` |
| `at_boundary` | Exactly MAX_LENGTH chars | `"a" * 255` |
| `url_input` | URL as field value | `https://evil.com/redirect` |
| `unicode` | Non-ASCII | `あいうえお🔥` |

Boundary max length is derived from field constraints in the scenario; defaults to 255 if unspecified. Read-only/navigation scenarios (no data-entry steps) get an assertion/navigation-oriented positive dataset instead of form-field values. `_llm_pipeline` also returns a `coverage_pct` signal — the percentage of the batch that got a usable positive dataset — and logs a warning below 50%.

---

## Script Generation — Action-Library Plan, Not Raw TypeScript

`ScriptGenerationAgent` (v2.1) never lets the LLM write TypeScript directly. It returns a validated **JSON test plan** built from a fixed action vocabulary and named locator keys; a deterministic renderer (`spec_renderer.py`) turns that plan into the `.spec.ts` file. This is what keeps generated tests structurally consistent and locator-safe regardless of what the model produces.

### The plan-JSON contract

- **Actions** — a fixed set (`ALLOWED_ACTIONS` in `agent.py`, mirroring the shared runtime's `ActionEngine.ts` 1:1): `navigate, click, doubleClick, hover, enterText, clearAndEnterText, pressKey, checkCheckbox, uncheckCheckbox, selectDropdownByText, selectDropdownByValue, scrollIntoView, waitForElement, waitForTimeout, dragAndDrop, uploadFile, verifyVisible, verifyHidden, verifyText, verifyContainsText, verifyValue, verifyEnabled, verifyDisabled, verifyChecked, verifyCount, verifyUrl, verifyUrlContains, verifyTitle, verifyTitleContains, takeScreenshot, goBack, reload, verifyNoPageErrors, useFlow`.
- **Locator keys** — only this scenario's slice of `locator_map.json` (translated from `scenario_element_map.json` via a reverse index), excluding any key that failed a live validation pass. The LLM is never offered a known-dead locator.
- **Flows** — reusable named sequences from `flows.json`, invoked via `{"action": "useFlow", "flow": "...", "args": {...}}`.

### Test counts

- **Positive tests scale with distinct functional clusters** SemanticMapAgent identified for the scenario — one test per cluster (dependent-sequence shape for a login-like flow, independent-siblings shape for a nav bar/filter set). This is uncapped: a scenario touching several functional areas produces more than one positive test.
- **`max_negative_cases` / `max_boundary_cases` / `max_data_iterations`** (`project.yaml`) remain a hard, final per-scenario ceiling (1/1 by default) — never scaled up by cluster count. What changes is *which* intent's data fills those fixed slots (highest-confidence first).

### Verification contract — no fabricated assertions

| Action type | What the test must assert |
|---|---|
| Positive click/navigate | The destination state changed (`verifyUrl`/`verifyVisible`/`verifyContainsText` on post-success content) — not "the click didn't throw." |
| Positive fill+submit | The real success indicator from the intent's `expected_result` / Test Data's `positive_dataset`. |
| Negative (bad/boundary data) | The matching positive success indicator is absent, or Test Data's `expected_error` indicator is present. |
| No genuine negative pathway | The negative slot is skipped entirely — never a fabricated placeholder assertion. |

`_drop_placeholder_negative_tests` mechanically enforces this: a `"negative"` test whose only assertion is a hardcoded empty-string check with no real `expected_error` anywhere in Test Data is dropped after validation (logged, not a hard failure) — the fix for an early real bug where a plain nav-menu click got a trivially-passing placeholder "negative" test.

### Page Object Model — where locators actually live

- `comprehension/dom_elements.json` — the raw discovery snapshot, untouched by this agent.
- **`test_creation/locator_map.json`** — one flat, project-wide file merge-written from every module's `dom_elements.json`. This is the *only* place a locator gets fixed: matched elements update in place, byte-identical relocated elements reuse the existing key, and only genuinely ambiguous adds/removals go to an LLM reconciliation call. An entry whose source element is confirmed gone is kept (never deleted) and flagged to `human_review_queue.json`.
- **`test_creation/pages.ts`** — one generated Page-factory class per module (a `constructor(page)` + one `Locator` getter per key) plus a `PAGE_REGISTRY`, regenerated every run. At test-run time, the shared runtime fixture resolves the spec's module, instantiates its Page class, and `ActionEngine` resolves every `locator_key` by property lookup on that instance.
- **Locator validation** — once per project per run, grouped by module (one headless browser launch per module), every `locator_map.json` entry is live-checked against the real page; a key must resolve to exactly one element (`count() == 1`, not just `> 0`) or it's excluded and flagged as drift.

### Known pitfalls — mechanically guarded, not just prompted

| Real failure observed | Guard |
|---|---|
| `enterText` filled a button because the real input was never discovered as its own locator | `_flag_action_locator_type_mismatches` drops any fill step whose resolved locator is role-typed button/link/checkbox/etc. |
| A `role` locator matched 2 elements (responsive duplicate buttons) — a Playwright strict-mode violation | Live validation requires `count() == 1`, not `count() > 0` |
| An `uploadFile` step referenced a file never created on disk | `ActionEngine.uploadFile()` throws an actionable "fixture not found" error; HealingAgent's `propose_fixture_fix` classifies it as not-healable rather than a locator bug |

Every `verify*` step carries a `message`; a step may carry `"soft": true` to collect the failure and keep running. Anything a scenario needs that isn't in the action/locator/flow vocabulary is reported in the plan's `missing_actions`/`missing_locators` and flagged to `human_review_queue.json` — never guessed.

---

## SemanticMapAgent — Preventing Prompt Bloat

A project can easily have 60+ DOM elements. Sending all of them to every script-generation call makes prompts unwieldy and produces lower-quality scripts.

`SemanticMapAgent` solves this with **one LLM call** before script generation: it maps each business scenario to the elements that scenario actually touches, and clusters them into functional groups with a confidence score (feeding ScriptGenerationAgent's positive-test-per-cluster scaling above).

```
dom_elements.json (63 elements) ──┐
business_scenarios.json (10) ─────┤
dom_intents.json (optional) ──────┤
                                  ▼
                       SemanticMapAgent (1 LLM call)
                                  │
                                  ▼
                     scenario_element_map.json
                     { "BS-007": { "relevant_elements": [
                         { "locator_id": "LOC-0002",
                           "playwright_expr": "page.getByPlaceholder('Search Products ...')",
                           "cluster": "search", "confidence": 0.92 } ] } }
```

After the LLM builds the map, the agent overwrites every `playwright_expr` with the authoritative value from `dom_elements.json` — the LLM cannot invent a locator that doesn't exist.

---

## Self-Healing — Multi-Call Diagnose → Repair → Verify Loop

`HealingAgent` is a native ADK agent — a Gemini-backed `LlmAgent` wrapped in an ADK `LoopAgent` — genuinely reasoning over each failure and calling tools across multiple turns, not a deterministic root-cause table. This is the platform's one real **multi-call, self-verifying agent**: it doesn't just generate a fix once — it applies it, re-runs the actual test, and keeps iterating if the fix didn't hold.

```python
tools = build_tools(ctx)
llm_agent = LlmAgent(name="healing_llm", model=model, instruction=SUPERVISOR_INSTRUCTION, tools=tools)
loop_agent = LoopAgent(name="healing_loop", sub_agents=[llm_agent], max_iterations=max_iterations)
```

`max_iterations` = `workflows/settings.yaml`'s `adk.healing_max_iterations` (default `3`). It operates at the **individual `test()` block level** — it never rewrites an entire spec file.

### The loop, concretely

1. **`read_failure_report`** — parses the Playwright JSON into structured failing-test entries, keyed by spec path (module subdirectories preserved). Tests Playwright itself marked `"flaky"` (failed once, passed on its own retry) are excluded — they already recovered.
2. The model diagnoses each failure's error message and calls a repair tool: `propose_locator_fix`, `propose_timing_fix`, `propose_compilation_fix`, `propose_test_data_fix`, `propose_navigation_fix`, `propose_fixture_fix` — or `mark_not_healable` if it's a real application/environment defect (never patched — rewriting expectations to match broken behavior is treated as worse than leaving it red).
3. **`apply_patch`** is the only tool allowed to write a `.spec.ts` file — structural validation (non-empty, balanced braces, a real `test`/`test.skip`/`test.fixme` block), then an atomic write. For specs generated by the action-library pipeline (`generation_mode: "action_library"`), a locator fix instead repairs `test_creation/locator_map.json` directly via `repair_named_locator()` — one shared-file fix heals every spec that references the same key.
4. **`run_tests`** re-executes just the patched spec(s) via `UIExecutionAgent` **to verify the fix actually worked** — this is the self-review step.
5. Loop ends via `tool_context.actions.escalate` once no failing tests remain, or naturally at `max_iterations` with `status: "partial"` (never silently reported as success).
6. `test_creation/test_suite.json` → `status: "healed"` for every spec with at least one applied patch.

### Structural safety boundary

No tool in `tools.py` can write `business_scenarios.json`, acceptance criteria, assertion expected values, `intents.yaml`/`dom_intents.json`, or any `workflows/*.yaml` — enforced by the tool surface having no path to those files, not by prompt instruction alone.

Requires `GOOGLE_API_KEY` in the environment. There is no CSS-based or other deterministic fallback — if Gemini/ADK is unavailable, `execute()` returns `status: "failed"` outright rather than silently degrading.

---

## Execution — Playwright TypeScript Mode

`UIExecutionAgent` auto-detects which mode to use by file presence:

```
test_scripts/
  ├── *.spec.ts found → npx playwright test (TypeScript mode)
  └── *.py only found → python -m pytest   (legacy backward-compat mode)
```

TypeScript mode shells out via `subprocess.Popen`:

```
npx playwright test <targets> --config playwright.config.ts --project=chromium
  [--headed] --workers=<1|2> [--grep <pattern>] --output=<html_dir>
```

| Situation | Response |
|-----------|----------|
| `node_modules/playwright/lib/program.js` absent | Fails fast — run `npm install` first. No installs during execution. |
| Playwright Chromium binary missing | Fails fast — run `npx playwright install chromium` first. |
| Exit code 4 (no tests collected) | Explicit warning log — NOT treated as success |
| `KeyboardInterrupt` mid-run | Partial-results summary, not a crash |
| Browser closed with no interaction (headed mode), 3× in a row | Auto-switches remaining specs to headless and re-runs them |
| Browser-close error on an individual test | Reclassified as `"skipped"`, not `"failed"` |
| Playwright's own `"flaky"` status (failed then passed on retry) | Counted as a pass |

Also supports suite-scoped runs and direct `spec_files` targeting — used by HealingAgent's `run_tests` tool to re-verify just the patched specs without re-running the whole project.

### Playwright configuration (`playwright.config.ts`)

| Setting | Value |
|---------|-------|
| `testMatch` | `**/test_scripts/**/*.spec.ts` |
| `retries` | 1 (2 on CI) |
| `workers` | 2 (1 on CI) |
| `timeout` | 60s per test; `expect.timeout` 10s; `actionTimeout` 15s; `navigationTimeout` 30s |
| `testIdAttribute` | `data-test` (not Playwright's default `data-testid`) |
| `screenshot` | on failure only |
| `video` / `trace` | on first retry |
| `baseURL` | `BASE_URL` env → scraped from the active project's `project.yaml` via `PW_PROJECT` → `http://localhost:3000` |
| `storageState` | `PW_STORAGE_STATE` env, if present (auth) |
| reporters | `list`, `json`, `html` (`open: 'never'`) |

---

## Suite Manifest: `test_suite.json`

`test_suite.json` is the single source of truth for test-run state per spec:

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

| Field | Meaning |
|-------|---------|
| `status` | `new` (Tier 0), `degraded_fallback` (Tier 2, Python raw-TS), `healed` (HealingAgent patched it) |
| `tier_used` | `0` = primary LLM, `1` = NS/alt-model, `2` = Python fallback |
| `generation_mode` | `"action_library"` for a plan-rendered spec, `null` for a raw-TS fallback spec — tells HealingAgent whether a locator fix should patch `locator_map.json` or the `.spec.ts` directly |

---

## Auxiliary Agents — Wired but Not in the Default Pipeline

These agents are registered in `agents/registry_setup.py` and fully functional, but none of the 8 `workflows/*.yaml` step lists currently invoke them:

| Agent | Folder | Status |
|-------|--------|--------|
| `SemanticDedupAgent` | `test_creation/dedup/` | Active. Single LLM call classifying proposed test cases as new coverage vs. duplicates. Not a workflow step — invoked directly, in-process, by `OrchestratorAgent._run_dedup()` right after `ArtifactGeneratorAgent` (testcases mode) proposes candidates. Fails open (`status: "partial"`, all approved) if the LLM is unavailable. |
| `ArtifactGeneratorAgent` | `test_creation/artifact_generator/` | Active, dual-mode (`intents` / `testcases` via `functools.partial`). An earlier-generation pipeline (intents → test cases → `application_assets/{project}/artifacts/*.yaml`) that predates the `semantic_map` → `script_generation` path now used in `full_workflow.yaml`. Both are registered; only the newer path is wired into any current workflow. |
| `LocatorAgent` | `test_execution/locator/` | Active, no LLM. Gap-filler: runs its own live DOM scan to assign locators to any `intents.yaml` entry still missing one (e.g. a BRD-only project later gains a URL). No-ops if no URL is available or everything is already grounded. |
| `ExecutionAgent` | `test_execution/execution/` | Active. Thin wrapper around `UIExecutionAgent` plus failure classification for healing. Documented alternate entrypoint — all current workflows call `UIExecutionAgent` directly under the `ui_execution` step name instead. |
| `BDDAgent` | `test_creation/bdd/` | **Stub only** (`status: "stub"`, no LLM). `execute()` returns a static placeholder. Disabled (`enabled: false`) in `workflows/agents.yaml`. |

---

## NeuroStack (NS) Integration

MTA connects to an optional NeuroStack server for any agent that has a registered NS endpoint.

**How it works:**
1. An NS registry YAML maps agent names to HTTP endpoints and expected response fields (path configured in `workflows/settings.yaml`'s `execution.ns.registry`)
2. When `FailureClassifier` routes to `NS_HTTP`, `NSHTTPConnector.call(agent_name, payload)` is used
3. Required response fields are validated; missing fields trigger the next fallback tier
4. Every NS call is logged in `human_review_queue.json` when the `HUMAN_REVIEW` route fires

**Configuration** (`workflows/settings.yaml`):
```yaml
connectors:
  llm: aws        # aws | external | gemini | internal | openai | ollama — shared by every agent

adk:
  models:                                                       # HealingAgent's ADK LlmAgent, per connector
    gemini: "gemini-2.0-flash"                                  # ADK native — bare model id
    aws: "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0"    # via LiteLLM
    external: "anthropic/claude-sonnet-4-6"
    openai: "openai/gpt-4o-mini"
    ollama: "ollama/llama3"
  healing_max_iterations: 3

execution:
  ns:
    base_url: "http://localhost:8000"
    auth_token_env: "NS_AUTH_TOKEN"
    registry: "workflows/ns_registry.yaml"    # optional; absent = NS disabled
```

`connectors.llm` picks the provider for every plain LLM-call agent; HealingAgent's ADK `LlmAgent` resolves its own model separately from `adk.models` via `connectors/adk_model.py::resolve_adk_model()` (native Gemini support, everything else routed through LiteLLM).

---

## Data Model — The Artifact Chain

```
URL + BRD
  └─ DiscoveryAgent
        ├─ comprehension/dom_elements.json       ← locator source of truth
        ├─ comprehension/business_scenarios.json ← scenario source of truth
        ├─ comprehension/interaction_catalog.json ← docs only; human-readable UI catalog
        └─ test_creation/intents.yaml            ← ui_scanner-sourced intent list

  └─ TestDataAgent
        └─ test_creation/test_data/test_data.json  ← up to 10 variant types per scenario

  └─ SemanticMapAgent
        └─ test_creation/scenario_element_map.json ← scenario → elements + functional clusters

  └─ ScriptGenerationAgent
        ├─ test_creation/locator_map.json          ← the one place a locator gets fixed
        ├─ test_creation/pages.ts                  ← generated Page Object Model
        ├─ test_creation/test_plans.json            ← validated JSON action-plan per scenario
        ├─ test_creation/test_scripts/{module}/test_*.spec.ts
        └─ test_creation/test_suite.json

  └─ UIExecutionAgent
        └─ test_execution/reports/json/{ts}_results.json

  └─ HealingAgent
        └─ patched .spec.ts / locator_map.json + test_suite.json (status: healed)

  └─ ReportingAgent
        └─ test_execution/reports/html/{ts}/
```

| Artifact | Produced by | Consumed by |
|----------|-------------|-------------|
| `dom_elements.json` | DiscoveryAgent | SemanticMapAgent, ScriptGenerationAgent, HealingAgent |
| `business_scenarios.json` | ComprehensionAgent | TestDataAgent, SemanticMapAgent, ScriptGenerationAgent |
| `test_data.json` | TestDataAgent | ScriptGenerationAgent |
| `scenario_element_map.json` | SemanticMapAgent | ScriptGenerationAgent |
| `locator_map.json` / `pages.ts` | ScriptGenerationAgent | UIExecutionAgent (runtime), HealingAgent |
| `test_BS-*.spec.ts` | ScriptGenerationAgent | UIExecutionAgent, HealingAgent |
| `test_suite.json` | ScriptGenerationAgent | UIExecutionAgent, HealingAgent, ReportingAgent |
| `{ts}_results.json` | UIExecutionAgent | HealingAgent, ReportingAgent |

---

## LLM Dependency Map

| Step | Needs LLM? | Tier-2 fallback (if LLM unavailable) |
|------|-----------|--------------------------------------|
| Discovery (DOM scan) | No | Playwright only |
| Discovery (scenarios) | Yes | Python DOM→scenario synthesizer (no NS hop) |
| TestDataAgent | Yes | NS HTTP → 3 fixed variants |
| SemanticMapAgent | Yes | NS HTTP → keyword-overlap scoring |
| ScriptGenerationAgent | Yes (per scenario) | NS HTTP → 1 positive test + skip stubs (off by default) |
| UIExecutionAgent | No | Playwright only |
| HealingAgent | Yes (multi-call, per block) | None — fails outright if Gemini/ADK unavailable |
| ReportingAgent | No | Aggregation only |

---

## Project Directory Layout

```
application_assets/projects/{project}/
├── project.yaml                            # project manifest (you create this)
├── project_state.json                      # fingerprint + run history cache
│
├── inputs/                                 # BRD documents (.md, .pdf, .docx, .txt)
│
├── comprehension/
│   ├── dom_elements.json                   ← locator source of truth
│   ├── business_scenarios.json             ← scenario source of truth
│   ├── interaction_catalog.json            ← docs-only UI catalog
│   └── modules/{module_id}/                ← per-module scan/scenario outputs (modular projects)
│
├── test_creation/
│   ├── intents.yaml                        ← ui_scanner-sourced intents
│   ├── locator_map.json                    ← project-wide named-locator map (the fix point)
│   ├── pages.ts                            ← generated Page Object Model
│   ├── scenario_element_map.json           ← scenario → relevant elements + clusters
│   ├── test_plans.json                     ← validated action-plan JSON per scenario
│   ├── test_suite.json                     ← suite manifest + per-spec status
│   ├── test_data/
│   │   ├── test_data.json
│   │   └── test_data.md
│   └── test_scripts/
│       └── {module_id}/test_{id}_{title}.spec.ts
│
├── test_suites/                            # named suite definitions (JSON only)
│   ├── smoke_suite.json
│   └── regression_suite.json
│
└── test_execution/
    └── reports/
        ├── index.json
        ├── json/{timestamp}_results.json
        └── html/{timestamp}/
```

---

## Architecture — One Agent, One Folder

Every agent — no exceptions — lives in its own folder with all 7 files present (real content, or an explicit `# Not used — ...` stub):

```
agents/<category>/<agent_name>/
├── __init__.py
├── agent.py       ← the ONLY acceptable main-file name
├── agent.md       ← prose spec: inputs, outputs, behavior, failure modes
├── agent.json     ← machine-readable manifest (name, llm_calls, inputs, outputs, dependencies, skills)
├── prompt.py       ← LLM prompt constant(s), or a stub
├── server.py       ← standalone CLI runner, or a stub
├── skills.py       ← AgentSkill entries, or a stub (`SKILLS: dict = {}`)
└── tools.py        ← re-exported tool functions, or a stub
```

```
agents/
├── orchestrator/                  ← workflow dispatch (flat — 1:1, no sub-agents)
│   └── agent.py                   ← OrchestratorAgent, step-driver + fallback-tier dispatch
│
├── comprehension/                 ← BRD ingestion + DOM/UI discovery
│   ├── discovery/                 ← DiscoveryAgent — mandatory gateway step
│   └── comprehension_agent/       ← ComprehensionAgent — BRD → business_scenarios.json
│
├── test_creation/                 ← test-artifact generation
│   ├── testdata/                  ← TestDataAgent
│   ├── semantic_map/              ← SemanticMapAgent
│   ├── script_generation/         ← ScriptGenerationAgent — action-plan → .spec.ts + Page Object Model
│   ├── dedup/                     ← SemanticDedupAgent (invoked in-process by the orchestrator)
│   ├── artifact_generator/        ← ArtifactGeneratorAgent (intents/testcases modes — earlier pipeline)
│   └── bdd/                       ← BDDAgent (stub)
│
├── test_execution/                ← test-run and result-handling
│   ├── ui_execution/              ← UIExecutionAgent — npx playwright test + pytest fallback
│   ├── execution/                 ← ExecutionAgent (wraps UIExecutionAgent; currently unwired)
│   ├── healing/                   ← HealingAgent — Gemini ADK LoopAgent, multi-call self-review
│   ├── locator/                   ← LocatorAgent — gap-filler DOM scan for ungrounded intents
│   └── reporting/                 ← ReportingAgent
│
├── common/                        ← SHARED across all agents
│   ├── failure_classifier.py      ← six-route FailureClassifier
│   ├── fallback_core.py           ← four deterministic Python fallbacks
│   └── review_queue.py            ← human_review_queue.json writer
│
├── base_agent.py                  ← execute_with_fallback() loop
├── registry.py                    ← AgentRegistry
└── registry_setup.py              ← build_default_registry(): every registered agent's wiring

tools/
├── suite_orchestrator.py          ← 4-level test execution tool (individual/module/suite/workflow)
├── playwright_scanner.py          ← the DOM scanner behind Discovery/LocatorAgent
├── scaffold_agent.py              ← generates a new agent's 7-file skeleton
├── test_creation/
│   └── script_generator/
│       ├── build_dom_locator_map.py  ← locator priority extraction + merge into locator_map.json
│       └── spec_renderer.py          ← deterministic action-plan → .spec.ts renderer
├── test_execution/
│   ├── healing/
│   └── reports/
├── auth/auth_setup.py
├── discovery/
│   ├── dom_scan.py
│   └── record_cli.py              ← --record interactive session capture
└── context/artifact_context.py

cli_appevolve.py                   ← AppEvolve-specific 4-level CLI
playwright.config.ts
package.json                       ← @playwright/test, vitest, typescript
workflows/
├── full_workflow.yaml             ← default 7-step pipeline
├── test_comprehension_only.yaml
├── test_test_creation_only.yaml
├── test_execution_only.yaml
├── test_execution_and_healing.yaml
├── healing_only.yaml
├── agents.yaml                    ← per-agent enable/disable
├── agent_registry.yaml            ← NS/python-stub fallback config per step
└── settings.yaml                  ← LLM connector, ADK models, NS server, logging
```

---

## Agent Evaluation (web app → Postgres)

Evaluates a user's app (AI agent, chatbot, form app, document generator, dashboard, API) from its GitHub repo, its
BRD and, when deployed, the live app itself. The workflow is `workflows/agent_evaluation.yaml`, driven by
`api/pipeline.py`. All state lives in Postgres, in tables owned by `frontend/prisma/schema.prisma` (schema changes go
through Prisma migrations: `frontend/prisma/README.md`).

The workflow is a **DAG**. Steps declare `needs` (what they wait for), `critical` (whether a failure stops the run),
`timeout_s` (a soft deadline) and `provides` (result keys; two steps that can run at the same time may not write the
same key). The code-evidence branch (repo analysis, traceability, review) runs alongside the browser branch
(discovery → … → pass/fail), which takes most of the wall-clock time.

| Step | Needs | What it does |
|---|---|---|
| repo_fetch | — | Resolves the default branch and commit first, then fetches the selected files at that commit (GitHub API, authenticated with `GITHUB_TOKEN` when set). Reports `repo_coverage` |
| repo_intelligence | repo_fetch | Deterministic knowledge graph and code chunks for Python, JS/TS and generic languages, cached per commit |
| repo_analysis | repo_fetch | Gemini app profile (purpose, interface). A failure degrades the profile instead of stopping the run |
| runtime_discovery | repo_intelligence | Browser crawl of the live app, logged in with the project's test account. Bounded by 12 pages, 40 visits and 10 min. Hands its session on to the executor |
| app_classification | runtime_discovery, repo_intelligence | Chatbot / Form Application / Document Generator / Dashboard / REST API / … |
| brd_builder | repo_analysis, runtime_discovery | The repo's BRD, or one written from the authenticated runtime profile or the code. Quote-verified requirements and atomic criteria |
| agent_test_generation | brd_builder, app_classification | Runtime tests only for criteria the discovered app can exercise, sized to the execution budget. None when nothing can run them; the reason is reported |
| action_generation | agent_test_generation, app_classification | Grounded browser/HTTP actions on discovered elements |
| playwright_executor | action_generation | Chromium with adaptive parallelism (document generators calibrate first, then drop back to serial if the app slows down) |
| evidence_collection → output_validation → pass_fail | (chain) | Evidence bundles, deterministic checks plus a quote-grounded judge, and verdicts (passed / failed / inconclusive / not executed, each with a reason) |
| live_agent_execution | pass_fail | Fallback for chat/API apps only. Never overwrites a recorded result |
| requirement_traceability | brd_builder, repo_intelligence | Static trace per criterion (retrieval, verifier samples, validated citations) |
| repository_review | repo_intelligence, repo_analysis | Scanner rules plus an LLM design review |
| brd_compliance | requirement_traceability, live_agent_execution | Merges runtime evidence into the static trace and builds the compliance matrix |
| compliance_scoring → final_report | (chain) | Score (`compliance-v1.2`), gates, recommendations and the report |

Submission modes: `brd_and_live`, `live_only` (the BRD is generated) and `brd_only` (code review only; no runtime
tests are generated).

```bash
# 1. evaluation service (repo root; reads GOOGLE_API_KEY from .env, DATABASE_URL from .env or frontend/.env)
.venv\Scripts\python -m uvicorn api.server:app --host 127.0.0.1 --port 8100
# 2. web app (apply pending migrations first)
cd frontend && npm run db:deploy && npm run dev      # http://localhost:3000 → Projects → New
```

Run lifecycle:
- A run is claimed only when a worker slot is free (`AQP_MAX_CONCURRENT_RUNS`, default 2); until then it stays `queued`.
- Running runs send a heartbeat every 30 s. Runs with no heartbeat for 10 min are failed automatically, as are runs interrupted by a restart.
- Users can cancel a run from the run page.
- Run artifacts (`.aqp_artifacts/runs/<id>`) are pruned after `AQP_ARTIFACT_RETENTION_DAYS` (default 30).

Security:
- Live URLs must be public hosts. Private, loopback and metadata addresses are refused, including on every redirect and every browser request. `AQP_ALLOW_PRIVATE_TARGETS=1` allows them for local development only.
- Chromium runs sandboxed (`AQP_CHROMIUM_SANDBOX=0` turns that off).
- Set the same `AQP_BACKEND_TOKEN` in `.env` and `frontend/.env`. Without it the service accepts only loopback callers.
- Untrusted text (repo files, BRDs, page text, the app's output) is fenced in every LLM prompt (`tools/agent_eval/untrusted.py`).

---

## Registered Agents (`agents/registry_setup.py`)

Agents are registered lazily via `build_default_registry(scope="all"|"mta"|"legacy")` (a module is imported on first use, so a broken legacy agent cannot take the evaluation service down); the legacy pipeline uses `scope="legacy"` with the keys below, the service `scope="mta"` with the 18 steps of `agent_evaluation.yaml`. `OrchestratorAgent` is constructed directly by `main.py` (not registry-dispatched — `registry_key: null`).

| Registry key | Class | In a current workflow step list? |
|---|---|---|
| `discovery` | `DiscoveryAgent` | Yes |
| `comprehension` | `ComprehensionAgent` | Invoked directly by DiscoveryAgent; kept registered for standalone use |
| `testdata` | `TestDataAgent` | Yes |
| `semantic_map` | `SemanticMapAgent` | Yes |
| `script_generation` | `ScriptGenerationAgent` | Yes |
| `ui_execution` | `UIExecutionAgent` | Yes |
| `healing` | `HealingAgent` | Yes |
| `reporting` | `ReportingAgent` | Yes (`always_run: true`) |
| `dedup` | `SemanticDedupAgent` | No — invoked in-process by the orchestrator |
| `artifact_generator_intents` / `artifact_generator_testcases` | `ArtifactGeneratorAgent` | No |
| `locator` | `LocatorAgent` | No |
| `execution` | `ExecutionAgent` | No |
| `bdd` | `BDDAgent` | No (stub, disabled) |

---

## Workflow Definitions (`workflows/*.yaml`)

| File | Steps |
|------|-------|
| `full_workflow.yaml` | discovery → testdata → semantic_map → script_generation → ui_execution → healing → reporting |
| `test_comprehension_only.yaml` | discovery |
| `test_test_creation_only.yaml` | testdata → semantic_map → script_generation |
| `test_execution_only.yaml` | ui_execution → reporting |
| `test_execution_and_healing.yaml` | ui_execution → healing → reporting |
| `healing_only.yaml` | healing → reporting (re-heals against the most recent existing report) |

Plus `agents.yaml` (per-agent enable/disable), `agent_registry.yaml` (NS/python-stub fallback config), and `settings.yaml` (connector/model/NS config).

---

## Modular Execution

After test scripts are generated, `tools/suite_orchestrator.py` (via `cli_appevolve.py`) supports 4 execution levels:

| Level | What runs | Command |
|-------|-----------|---------|
| **1 — individual** | Single `.spec.ts` | `python cli_appevolve.py test --level 1 --file test_SC-001_search_products.spec.ts` |
| **2 — module** | All specs in a module dir | `python cli_appevolve.py test --level 2 --module module_dashboard` |
| **3 — suite** | Named JSON suite | `python cli_appevolve.py test --level 3 --suite smoke` |
| **4 — workflow** | Multi-step workflow spec | `python cli_appevolve.py test --level 4 --workflow complete_flow` |

**Suite definitions** live in `test_suites/` as JSON:

```json
// smoke_suite.json
{
  "suite_id": "smoke",
  "scenarios": ["SC-001", "SC-002", "SC-003"],
  "execution": { "headless": true, "retries": 1, "parallel": 3 }
}
```

```bash
python cli_appevolve.py list suites
python cli_appevolve.py list modules
python cli_appevolve.py test --level 3 --suite smoke --headed
```

`SuiteOrchestrator` can also be called directly from the orchestrator agent for selective re-execution: `from tools.suite_orchestrator import SuiteOrchestrator`.

---

## Running the Platform

```bash
# Install dependencies
pip install -r requirements.txt
npm install
npx playwright install chromium

# Run a project (full pipeline)
python main.py --project AppEvolve

# Run a specific workflow (see Workflow Definitions above)
python main.py --project AppEvolve --workflow test_test_creation_only

# Run pipeline for one module only
python main.py --project AppEvolve --module M01

# Force re-discovery / re-execution even without detected changes
python main.py --project AppEvolve --force-rediscover --force-execute

# Run a named suite (bypasses the new_additions guard)
python main.py --project AppEvolve --suite smoke

# Print persistent project state and exit
python main.py --project AppEvolve --show-state

# One-time auth capture (see Auth Setup below)
python main.py --project AppEvolve --auth-setup

# Human-guided interactive recording (interactive_scan: true projects)
python main.py --project AppEvolve --module M01 --record

# Run Playwright tests directly (bypassing the Python orchestrator)
PW_PROJECT=AppEvolve npx playwright test --headed
npx playwright show-report playwright-report/html
```

**Disabling agents** — edit `workflows/agents.yaml`:
```yaml
agents:
  healing:
    enabled: false   # skip healing
  ui_execution:
    enabled: false   # script generation only
```

---

## Adding a New Agent

**Must be created via the scaffold script** — do not hand-create agent folders:

```bash
python tools/scaffold_agent.py --name <agent_name> \
    --category <comprehension|test_creation|test_execution|orchestrator> \
    [--has-llm] [--has-tools] [--has-server] [--dry-run]
```

This generates all 7 files with real-or-explicit-stub content. It deliberately does **not** touch `agents/registry_setup.py` or `workflows/*.yaml` — it prints a "next steps" checklist instead, since wiring a new agent into the orchestrator has real side effects (registry key naming, workflow step ordering).

```python
class MyAgent(BaseAgent):
    MODULE_NAME = "my_module"

    def execute(self, request, state):
        return self.execute_with_fallback(request, state)   # ← routes through FailureClassifier

    def _run_primary(self, request, state):
        ...  # LLM call

    def _run_py_fallback(self, request, state):
        from agents.common import fallback_core
        ...  # deterministic fallback — same output format as _run_primary
```

Then: register in `agents/registry_setup.py`, add the step to the relevant `workflows/*.yaml`, and optionally add an NS endpoint.

See `agents/test_creation/dedup/` for a small, single-file-per-concern reference example with every template file correctly filled.

---

## Auth Setup

For applications behind a login wall, run a one-time auth capture before the main pipeline. The captured session (cookies + localStorage) is reused by the DOM scanner and every generated Playwright spec.

### 1. Add an `auth:` block to `project.yaml`

**Strategy: `storageState`** (SSO / OAuth / any manual login) — opens a headed browser, you complete the login, MTA waits for `wait_for_url`:

```yaml
auth:
  enabled: true
  strategy: storageState
  setup_url: https://app.example.com/login
  storage_state_path: application_assets/projects/myapp/.auth/auth.json
  wait_for_url: https://app.example.com/dashboard
```

**Strategy: `credentials`** (username + password form, fully automated) — reads credentials from environment variables, fills the form automatically:

```yaml
auth:
  enabled: true
  strategy: credentials
  setup_url: https://app.example.com/login
  storage_state_path: application_assets/projects/myapp/.auth/auth.json
  wait_for_url: https://app.example.com/dashboard
  username_env: APP_USERNAME
  password_env: APP_PASSWORD
  username_selector: "#email"
  password_selector: "#password"
  submit_selector: "button[type=submit]"
```

### 2. Run auth setup

```bash
export APP_USERNAME=you@example.com
export APP_PASSWORD=yourpassword
python main.py --project myapp --auth-setup
```

Saves `auth.json` to `storage_state_path`. Re-run when your session expires. The DOM scanner and every generated spec automatically load it — no extra flags needed at pipeline run time.

---

## Testing Requirements (Claude Code rule)

All code changes made by Claude in this project must include unit tests. The rule lives globally at `~/.claude/rules/testing-requirements.md` and applies across all projects:

- **Unit tests are required** before any task is marked complete — written and run with output shown.
- **Integration tests are optional** — Claude will ask before writing them.
- Excluded from the rule: documentation-only edits, comments, whitespace changes, and version bumps with no code impact.

Run the project's test suites:

```bash
pytest                        # Python unit tests
npm run test:unit             # TypeScript/vitest unit tests
npx playwright test           # Playwright integration / E2E tests
```
