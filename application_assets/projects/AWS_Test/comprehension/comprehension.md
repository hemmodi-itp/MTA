# Comprehension

This folder holds the outputs of **Module 1** (Discovery): the DOM scan from DiscoveryAgent and the BRD analysis from ComprehensionAgent. All files here are written by the pipeline — do not edit them manually.

---

## File inventory

### Global outputs (written once per pipeline run)

- **`dom_elements.json`** — Every interactable DOM element found on the target URL. Each entry includes:
  - `locator_id` (LOC-0001..N) — stable reference ID
  - `playwright_locators` — semantic Playwright expressions (`getByPlaceholder`, `getByRole`, `getByText`)
  - `recommended_locator` — best CSS/attribute selector
  - `technical_locators.css` — positional CSS (last resort, fragile)
  - `tag`, `placeholder`, `aria_label`, `text_content`, `description`

- **`business_scenarios.json`** — Flat list of all testable scenarios extracted from BRD documents across all modules. Each scenario has:
  - `scenario_id` — either legacy hyphenated (`BS-001`, `SC-001`) or module-scoped (`M01_BS_001`); both forms are supported end-to-end (execution, healing, catalog, suites)
  - `title`, `business_objective`, `actor`, `preconditions[]`
  - `steps[]` — ordered sequence of user actions and system responses
  - `expected_result`, `business_rules[]` (rule IDs from the BRD, e.g. `BR-01`), `traceability[]` (source file/section/requirement_id)
  - `confidence_score` — 1.0 for LLM-comprehended scenarios; 0.75 for the DOM-only synthetic fallback
  - `module_id`, `module_name` — which module this scenario belongs to

- **`business_scenarios.md`** — Human-readable rendering of `business_scenarios.json` for QA review.

- **`run_summary.json`** — Summary of the last discovery run: mode, scenario count, DOM element count, timestamp.

- **`synthetic_brd.md`** — Only written when a module has a URL but no usable BRD file (or BRD comprehension failed/timed out) — DiscoveryAgent falls back to synthesizing scenarios directly from the DOM scan, and records what it inferred here for review.

### Per-module outputs (written under `modules/`)

When the pipeline runs with `--module M01`, the DOM-scan outputs are scoped to that module:

```
comprehension/
└── modules/
    └── M01/
        ├── dom_elements.json    ← elements found on M01's URL only
        └── dom_intents.json     ← intents inferred for M01's URL only
```

**Business scenarios are never split per module on disk.** Every scenario — regardless of which
module it came from — lands in the single flat `comprehension/business_scenarios.json`, tagged with
a `module_id` field. There is no `modules/<name>/scenarios.json` file; filter the flat list by
`module_id` instead.

### Interactive scan outputs (only when `interactive_scan: true`)

- **`interactive/session.json`** — Raw click, navigation, and API events recorded during the session.
- **`interactive/user_flows.json`** — Assembled user flows with confidence=0.95 (used directly as scenarios).
- **`.scan_checkpoint.json`** — Mid-session checkpoint for crash recovery. Deleted on clean session end.

---

## Produced by

| File | Agent |
|------|-------|
| `dom_elements.json` | DiscoveryAgent (DOM scan, no LLM) |
| `dom_intents.json` | DiscoveryAgent (intent extraction, no LLM) |
| `business_scenarios.json` / `.md` | ComprehensionAgent (BRD comprehension, LLM) — or DiscoveryAgent's DOM-only synthetic fallback when BRD comprehension fails/times out |
| `synthetic_brd.md` | DiscoveryAgent (DOM-only fallback path) |
| `interactive/` | DiscoveryAgent with `interactive_scan: true` |

---

## Consumed by

| File | Consumed by |
|------|-------------|
| `dom_elements.json` | SemanticMapAgent, ScriptGenerationAgent, HealingAgent |
| `business_scenarios.json` | TestDataAgent, SemanticMapAgent, ScriptGenerationAgent |

`dom_intents.json` from here is translated into `test_creation/intents.yaml` early in the discovery
step — see `test_creation/artifacts.md`.

---

## File types allowed

`.json` and `.md` only. Do not place BRD source files here — those live in `inputs/`.
