# Discovery

This folder holds the outputs of the **DiscoveryAgent**, which performs a live browser scan of the target application URL and builds a structured inventory of the DOM. Discovery runs against the real application and produces the locator data that ScriptGenerationAgent needs to write accurate Playwright selectors.

All files here are written by the pipeline — do not edit them manually.

---

## What belongs here

- **`dom_elements.json`** — Inventory of every interactive DOM element found on the scanned page. Each entry includes:
  - `locator_id` (LOC-0001..N) — stable reference ID used across all downstream artifacts
  - `playwright_locators` — priority-ordered Playwright expressions
  - `recommended_locator` — best single-expression selector for this element
  - `tag`, `aria_label`, `placeholder`, `text_content`, `description`

- **`dom_intents.json`** — Intent suggestions inferred from the DOM: what a user can click, fill, select, or assert on this page. Raw input to intent mapping — later translated into `test_creation/intents.yaml`.

- **`run_summary.json`** — Summary of the discovery run: URL, scan mode, element count, scenario count, timestamp. Written once per run, at the same scope (project-level or per-module) as the rest of that run's outputs.

---

## Modular discovery

When running with `--module M01`, DiscoveryAgent scans **only the URL defined for that module** in `project.yaml`. The outputs (`dom_elements.json`, `dom_intents.json`) reflect that single page.

Running without `--module` scans the project-level URL and uses all modules' BRD files together.

---

## Scan modes

| Mode | How it works |
|------|-------------|
| Automated (`interactive_scan: false`) | Headless or headed Playwright crawl — no user input needed |
| Interactive (`interactive_scan: true`) | Headed browser opens; user navigates freely; scanner records elements and flows |

For the interactive mode, the scanner also writes under `interactive/`:
- `session.json` — raw event log of clicks, navigation, form fills
- `user_flows.json` — assembled user journeys (confidence=0.95, treated as scenarios)
- `.scan_checkpoint.json` — crash-recovery checkpoint (auto-deleted on clean finish)

---

## Produced by

DiscoveryAgent launches a browser session against the module URL, extracts element data, and infers interaction intents. Runs before any test creation step.

## Consumed by

- **SemanticMapAgent** — maps each scenario to 3-7 relevant DOM elements from `dom_elements.json`
- **ScriptGenerationAgent** — reads locators from `dom_elements.json` via the semantic map
- **HealingAgent** — uses `dom_elements.json` as the reference when locators break after UI changes

---

## File types allowed

`.json` only.
