# Comprehension

This folder holds the outputs of **Module 1** (Discovery): the DOM scan from DiscoveryAgent and the BRD analysis from ComprehensionAgent.

## What belongs here

- `dom_elements.json` — Every interactable DOM element found on the target URL. Each element entry includes:
  - `locator_id` (LOC-0001..N) — stable reference ID
  - `playwright_locators` — semantic Playwright expressions (`getByPlaceholder`, `getByRole`, `getByText`)
  - `recommended_locator` — best CSS/attribute selector
  - `technical_locators.css` — positional CSS (last resort, fragile)
  - `tag`, `placeholder`, `aria_label`, `text_content`, `description`

- `business_scenarios.json` — Testable business scenarios extracted from BRD documents. Each scenario has:
  - `scenario_id` (BS-001..N)
  - `title`, `actor`, `goal`, `preconditions`
  - `steps[]` — ordered sequence of user actions and system responses
  - `expected_outcomes`, `acceptance_criteria`

- `business_scenarios.md` — Human-readable rendering of `business_scenarios.json` for QA review.

- `interaction_catalog.json` — **Documentation only.** Human-readable catalog of "what can be clicked, filled, or selected" on the page. Replaces the old `intents.yaml` for human visibility. NOT wired into the locator resolution chain.

## `interaction_catalog.json` format

```json
{
  "catalog": [
    {
      "catalog_id": "IC-001",
      "label": "Product Search Input",
      "locator_id": "LOC-0002",
      "playwright_expr": "page.getByPlaceholder('Search Products ...')",
      "action": "fill",
      "description": "Main product search field on the Test Stations page"
    }
  ]
}
```

## Produced by

- **DiscoveryAgent** (DOM scan, no LLM) → `dom_elements.json`
- **ComprehensionAgent** (BRD comprehension, LLM) → `business_scenarios.json`, `business_scenarios.md`
- **DiscoveryAgent** post-processing → `interaction_catalog.json` (synthesised from dom_elements.json)

## Consumed by

- **TestDataAgent** — reads `business_scenarios.json` + `interaction_catalog.json` (if available)
- **SemanticMapAgent** — reads `business_scenarios.json` + `dom_elements.json`
- **ScriptGenerationAgent** — reads `scenario_element_map.json` + `business_scenarios.json` (locators come from dom_elements.json via the semantic map, not from this folder directly)

## File types allowed

`.json` and `.md` only.
