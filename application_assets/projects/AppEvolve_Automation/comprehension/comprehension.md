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
  - `scenario_id` (SC-001..N)
  - `title`, `actor`, `goal`, `preconditions`
  - `steps[]` — ordered sequence of user actions and system responses
  - `expected_outcomes`, `acceptance_criteria`
  - `module_id` — which module this scenario belongs to

- **`business_scenarios.md`** — Human-readable rendering of `business_scenarios.json` for QA review.

- **`run_summary.json`** — Summary of the last discovery run: mode, scenario count, DOM element count, timestamp.

### Per-module outputs (written under `modules/`)

When the pipeline runs with `--module M01`, module-scoped scenario files are written here:

```
comprehension/
└── modules/
    ├── module_dashboard/
    │   └── scenarios.json      ← scenarios belonging to the dashboard module
    ├── module_navigation/
    │   └── scenarios.json      ← scenarios belonging to the navigation module
    └── module_login/
        └── scenarios.json      ← scenarios belonging to the login module
```

Each `scenarios.json` has the same schema as `business_scenarios.json` but scoped to one module.

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
| `business_scenarios.json` / `.md` | ComprehensionAgent (BRD comprehension, LLM) |
| `modules/*/scenarios.json` | ComprehensionAgent (per-module run) |
| `interactive/` | DiscoveryAgent with `interactive_scan: true` |

---

## Consumed by

| File | Consumed by |
|------|-------------|
| `dom_elements.json` | SemanticMapAgent, ScriptGenerationAgent, HealingAgent |
| `business_scenarios.json` | TestDataAgent, SemanticMapAgent, ScriptGenerationAgent |
| `modules/*/scenarios.json` | ScriptGenerationAgent (per-module script generation) |

---

## File types allowed

`.json` and `.md` only. Do not place BRD source files here — those live in `inputs/`.
