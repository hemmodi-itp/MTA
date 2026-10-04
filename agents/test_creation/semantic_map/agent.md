# SemanticMapAgent

Prevents dumping all 63+ DOM elements into every script generation LLM call. One LLM call maps each
scenario to its relevant 3-7 elements — and, on top of that LLM pass, a deterministic Python layer
clusters this module's DOM intents into functional buckets (e.g. username / password /
forgot-password / forgot-username → one "login" cluster) and scores each scenario's relevance against
those clusters. Its real job isn't "pick 3-7 arbitrary elements" — it's *group related intents, then
suggest a whole functional bucket together* when a scenario touches that area.

## Inputs
- `comprehension/business_scenarios.json` (required)
- `comprehension/dom_elements.json` (required)
- `comprehension/modules/{module_id}/dom_intents.json` (optional — module-scoped, read via
  `tools/discovery/dom_intents.py::load_dom_intents`; absent for BRD-only projects, see mode table
  below)
- `comprehension/modules/{module_id}/interactive/user_flows.json` (optional — only present for
  `interactive_scan: true` projects; recorded click sequences are a stronger, ground-truth clustering
  signal than keyword overlap and override it where they overlap)

## Outputs
- `test_creation/scenario_element_map.json`
- `test_creation/intents.yaml` (side effect — this module's matched intents get their
  `source_scenarios` backlinked; every other module's entries are left untouched, mirroring
  `DiscoveryAgent._save_intents_yaml`'s per-module merge rule)

## Output format

`relevant_elements` entries always carry `locator_id`/`playwright_expr`/`relevance`. When
`dom_intents.json` was available, they also carry `intent_id`/`action`/`expected_result`/`cluster`/
`confidence`:

```json
{
  "M01_BS_001": {
    "scenario_title": "Test login functionality",
    "relevant_elements": [
      {
        "locator_id": "LOC-0002",
        "playwright_expr": "page.getByPlaceholder('Username')",
        "relevance": "primary username input",
        "intent_id": "DOM_INT_001",
        "action": "fill",
        "expected_result": null,
        "cluster": "login",
        "confidence": 0.9
      }
    ]
  }
}
```

## How clustering + confidence work (`tools.py`)

- `build_intent_clusters` — union-find over normalized intent-name token overlap (no embeddings, no
  extra LLM call). `enter_username`/`enter_password`/`click_forgot_password` land in one cluster
  because they share the `username`/`password` tokens.
- `apply_user_flow_clusters` — when `interactive_scan: true`, elements touched within the same
  recorded flow (e.g. sign in → search mobile → click add to cart) are unioned into one flow-labelled
  cluster, overriding the keyword-based guess for those elements.
- `score_scenario_relevance` — keyword-overlap confidence between a scenario's title/steps/BRD
  traceability text and each intent, then boosted so every intent sharing a cluster with a directly
  matched intent inherits that match's confidence too (a BRD mentioning "products" boosts the whole
  products/search/pricing cluster, not just whichever intent name happens to contain "products"
  literally).
- `backlink_source_scenarios` — writes the scenario → intent_id matches back into `intents.yaml`,
  scoped to this module_id only. This is what makes `TestDataAgent`'s legacy `intents.yaml` field-name
  hint loader (`_load_fill_fields_from_intents`) actually work — previously `source_scenarios` was
  always `[]` because the only thing that ever populated it (`ArtifactGeneratorAgent`'s `testcases`
  pass) isn't wired into the active `full_workflow.yaml`.

## Locator resolution

`tools.py`'s `build_locator_map` overwrites any LLM-hallucinated `playwright_expr` with the
authoritative one derived directly from `dom_elements.json` — the LLM's job is only to pick *which*
elements are relevant per scenario, not to invent selector syntax.

## Discovery mode behavior (BOTH / URL ONLY / BRD ONLY)

Mirrors `agents/comprehension/discovery/agent.md`'s mode table — this agent never launches a scan
itself, it just reads whatever discovery already produced:

| Mode | `dom_intents.json` / `user_flows.json` available? | Effect here |
|---|---|---|
| BOTH / URL ONLY | Yes | Full clustering + confidence + `intents.yaml` backlink |
| BRD ONLY | No | `_enrich_with_intents` is a graceful no-op — `relevant_elements` keeps only the plain `locator_id`/`playwright_expr`/`relevance` fields it already had from the element-relevance LLM pass |

## Fallback behaviour
- **FALLBACK** → `fallback_core.fallback_semantic_map()` — keyword overlap scoring (no LLM); top-5
  elements per scenario. Still goes through the same intent-clustering/confidence/backlink enrichment
  afterward, so a fallback-tier run isn't left permanently thinner than a primary-tier one.
