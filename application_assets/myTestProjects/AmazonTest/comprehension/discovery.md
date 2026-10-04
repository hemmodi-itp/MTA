# Discovery

This folder holds the outputs of the **DiscoveryAgent**, which performs a live browser crawl of the target application URL and builds a structured inventory of the DOM. Discovery runs against the real application and produces the locator data that the ScriptGenerationAgent needs to write accurate Playwright selectors.

## What belongs here

- `manifest.json` — A high-level map of the application's page structure: all discovered routes, major UI sections, component counts, and navigation paths. Gives the pipeline a structural overview before generating scripts.
- `dom_elements.json` — A raw inventory of interactive DOM elements found across all crawled pages. Each entry includes the element's selector, role, label, tag, and page context. This is the source of truth for all locators used in test scripts.
- `dom_intents.json` — A resolved mapping from test intents (defined in `artifacts/intents.yaml`) to the specific DOM elements that fulfil them. Bridges the abstract intent layer and the concrete selector layer so scripts can be generated without hardcoding selectors.

## Produced by

The DiscoveryAgent launches a headless (or headed) browser session against the URL in `project.yaml`, crawls all reachable pages, and extracts element data. It should run after `artifacts/intents.yaml` exists so it can produce the intent-to-element mapping in `dom_intents.json`.

## Consumed by

- **ScriptGenerationAgent** — reads `dom_intents.json` and `dom_elements.json` to resolve selectors when generating Playwright scripts
- **HealingAgent** — uses `dom_elements.json` as a reference when locators in existing scripts break after UI changes

## File types allowed

`.json` only.

Do it for these functionalities only. 
