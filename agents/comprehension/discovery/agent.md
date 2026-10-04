# DiscoveryAgent

DiscoveryAgent is the mandatory gateway step for every QA workflow.
It runs **before** any other agent and decides what discovery work to do based on the inputs
declared in `inputs/projects/{project}/project.yaml`.

If DiscoveryAgent fails with `blocking=True`, **the orchestrator stops immediately** — no
downstream agent runs until discovery succeeds.

---

## Inputs (from `project.yaml`)

| Key | Required | Description |
|-----|----------|-------------|
| `url` | conditional | Target application URL for DOM scan |
| `brd_dir` | conditional | Path to BRD document or directory |
| `project_name` | yes | Used to derive output paths |
| `application_name` | no | Defaults to `project_name` |
| `browser` | no | `chromium` (default), `firefox`, `webkit` |
| `headless` | no | `true` (default) |

At least one of `url` or `brd_dir` must be present.

### `interactive_scan: true` projects

When `project.yaml`'s `project.interactive_scan` is `true`, DiscoveryAgent
does **not** launch a live browser itself — a human must record the module
first, outside this timed step, via:

```
python main.py --project <name> --module <id> --record
```

This opens a real browser with a "Finish Recording" banner; the human
explores the app and closes the banner (or the browser) when done. Recorded
elements/clicks are written to `comprehension/dom_elements.json` etc.
(module-scoped when the project declares `modules`). DiscoveryAgent then
reads those files — a fast disk operation with no timeout — rather than
racing a human-paced session against a wall-clock pipeline deadline. If no
recording is found, discovery fails with `blocking=True` and a message
naming the exact `--record` command to run.

---

## Decision Rules

The mode is selected by which inputs are present:

```
url present AND brd_dir present → BOTH
url absent  AND brd_dir present → BRD ONLY
url present AND brd_dir absent  → URL ONLY
url absent  AND brd_dir absent  → NONE  (immediate blocking failure)
```

---

## Mode: BOTH

**Trigger:** `url` and `brd_dir` both present in project.yaml.

### Execution
1. Launch **two parallel tasks** on plain daemon threads (not ThreadPoolExecutor —
   a wedged task must never block process exit):
   - Task A: DOM scan → `comprehension/dom_elements.json` (or `comprehension/modules/{module_id}/dom_elements.json` for modular projects) → `comprehension/dom_intents.json` (module-scoped alongside dom_elements.json)
   - Task B: ComprehensionAgent reads BRD → `comprehension/business_scenarios.json` + `.md`
2. After both tasks complete, if DOM scan passed → save DOM intents as `test_creation/intents.yaml`
   (marked `source: ui_scanner`).
3. **Fallback:** if Task B (BRD comprehension) failed but Task A (DOM scan) passed:
   - Python rule-based synthesizer converts DOM intents directly to `business_scenarios.json` + `.md`
   - No LLM call — works even when AWS credentials are expired
   - Result carries `comprehension_source: "dom_synthesized"`, `confidence_score: 0.75`

### Mandatory outputs
All three files must exist after execution. If any are missing the step fails with `blocking=True`.

| File | Location | Source |
|------|----------|--------|
| `intents.yaml` | `application_assets/{project}/test_creation/` | DOM scan |
| `business_scenarios.json` | `application_assets/{project}/comprehension/` | ComprehensionAgent |
| `business_scenarios.md` | `application_assets/{project}/comprehension/` | ComprehensionAgent |

---

## Mode: URL ONLY

**Trigger:** `url` present, `brd_dir` absent (or path does not exist).

### Execution (sequential)
1. **Step 1** — DOM scan → `comprehension/dom_elements.json` (or `comprehension/modules/{module_id}/dom_elements.json` for modular projects) + `comprehension/dom_intents.json` (module-scoped alongside dom_elements.json).
   - If scan fails → return `status=failed, blocking=True` immediately.
2. **Step 2** — Save DOM intents as `test_creation/intents.yaml` (marked `source: ui_scanner`).
3. **Step 3 (primary)** — Synthesise BRD markdown → `comprehension/synthetic_brd.md`
   → ComprehensionAgent (LLM) → `comprehension/business_scenarios.json` + `.md`.
   - Result carries `comprehension_source: "ui_scanner"`.
4. **Step 3 (fallback — if LLM unavailable)** — If ComprehensionAgent raises any exception
   (expired AWS token, missing credentials, network error), the Python rule-based synthesizer
   runs instead: DOM intents are grouped into `BusinessScenario` objects directly, no LLM call.
   - Result carries `comprehension_source: "dom_synthesized"`.
   - All scenarios produced this way have `confidence_score: 0.75` as a synthetic marker.

### Mandatory outputs
| File | Location | Source |
|------|----------|--------|
| `intents.yaml` | `application_assets/{project}/test_creation/` | DOM scan |
| `business_scenarios.json` | `application_assets/{project}/comprehension/` | ComprehensionAgent (synthetic BRD) |
| `business_scenarios.md` | `application_assets/{project}/comprehension/` | ComprehensionAgent (synthetic BRD) |

---

## Mode: BRD ONLY

**Trigger:** `brd_dir` present, `url` absent.

### Execution
1. ComprehensionAgent reads BRD → `comprehension/business_scenarios.json` + `.md`.

### Mandatory outputs
| File | Location | Source |
|------|----------|--------|
| `business_scenarios.json` | `application_assets/{project}/comprehension/` | ComprehensionAgent |
| `business_scenarios.md` | `application_assets/{project}/comprehension/` | ComprehensionAgent |

`intents.yaml` is **optional** for this mode — it will be generated in the
`artifact_generator_intents` step by LLM from business scenarios.

### Note on test execution
With no URL, LocatorAgent cannot run a DOM scan, so locators cannot be assigned.
Workflow steps that depend on locators (execution, healing) should be disabled in
`config/agents.yaml` for BRD-only runs, or they will fail gracefully with a clear error.

---

## Mode: NONE

**Trigger:** neither `url` nor `brd_dir` present.

Returns `status=failed, blocking=True` immediately with error:
```
No valid input found in project.yaml.
Provide 'url', 'brd_dir', or both.
Workflow cannot continue.
```

---

## Output: `test_creation/intents.yaml` format

When DiscoveryAgent writes `intents.yaml` (BOTH and URL ONLY modes), it uses this schema:

```yaml
project: alterdomus
source: ui_scanner          # always "ui_scanner" when written by DiscoveryAgent
intents:
  - intent_id: INT-001
    intent_name: enter_email
    action: fill
    locator_id: LOC-0001
    value: null
    expected_result: null
    source_scenarios: []    # populated by ArtifactGeneratorAgent in testcases pass
```

Downstream agents (`TestDataAgent`, `ArtifactGeneratorAgent testcases`, `LocatorAgent`)
all read from `test_creation/intents.yaml`.

---

## Output: run summary

After every run, DiscoveryAgent writes a machine-readable summary to:

```
application_assets/{project}/comprehension/run_summary.json
```

(or `comprehension/modules/{module_id}/run_summary.json` for modular projects)

Fields include `mode`, `status`, `blocking`, `dom_intents_count`, `scenarios_count`,
`missing_outputs`, `comprehension_source`, `module_id`, and paths to every artifact produced.

---

## Blocking failure behaviour

When mandatory outputs are missing after a mode completes, DiscoveryAgent sets
`blocking=True` in its return dict.

The OrchestratorAgent checks for this flag after every step:

```python
if step_status == "failed" and result.get("blocking"):
    logger.error("Blocking failure — aborting remaining workflow steps.")
    break
```

No further steps execute until discovery succeeds and all mandatory files are present.

**To recover:** fix the root cause (expired LLM credentials, unreachable URL, wrong BRD
path), then re-run `python main.py` with the same request.

---

## File locations (full output tree)

```
application_assets/{project}/
├── comprehension/
│   ├── dom_elements.json           ← BOTH, URL ONLY  (locator source of truth)
│   ├── business_scenarios.json     ← ALL modes       (mandatory)
│   ├── business_scenarios.md       ← ALL modes       (mandatory)
│   └── interaction_catalog.json    ← BOTH, URL ONLY  (docs only; human-readable UI catalog)
└── discovery/
    ├── manifest.json               ← always written
    └── synthetic_brd.md            ← URL ONLY (and BOTH fallback)
```

## interaction_catalog.json — docs only

`interaction_catalog.json` is produced by DiscoveryAgent from `dom_elements.json`. It is a human-readable catalog of "what can be clicked, filled, or selected" on the page — the successor to `intents.yaml` for visibility purposes. It is **NOT** wired into the locator resolution chain; ScriptGenerationAgent reads locators from `dom_elements.json` via `scenario_element_map.json`, not from this file.
