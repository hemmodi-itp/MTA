# ComprehensionAgent

Reads BRD (requirement) documents and produces structured Business Scenarios via a five-step
pipeline:

```
parse_all_documents (or parse_document, per-module)
    → [requirements.enabled] tools.requirements.service.extract_for_module   (1 LLM call per BRD)
        → test_comprehension/requirements.json   (per-module upsert)
    → extract_requirements   (LLM, per document)
    → generate_business_scenarios  (LLM, combined; told the module's ACs when enabled)
    → validate_business_scenarios
    → [requirements.enabled] link scenarios to ac_ids
    → export_scenarios
        → application_assets/projects/<project>/test_comprehension/
            business_scenarios.json
            business_scenarios.md
```

Registered as `"comprehension"` — but invoked directly by `DiscoveryAgent`
(`agents.comprehension.discovery.agent`) as a plain Python import, not through the registry. Also
called as an NS fallback tier before DOM-synthesis when the local LLM call fails.

## Modes

- **Flat** (`_execute_flat`) — default when `request["modules"]` is absent. Parses the whole
  `input_dir`, runs the five-step pipeline once, writes one `business_scenarios.json`.
- **Modular** (`_execute_modular`) — when `request["modules"]` is a list of `{id, name, brd_file}`
  dicts. Each module's BRD file is parsed and processed separately; scenarios are tagged with their
  `module_id`, and existing titles per module are loaded first (`load_existing_titles_by_module`) so
  re-runs don't duplicate scenarios already generated for that module.

## Inputs
- `project_name` (falls back to `request["message"]`, then `"project"`)
- `brd_dir` or `input_dir` (defaults to `application_assets/<project>/inputs/`)
- `modules` (optional — list of module dicts; presence switches to modular mode)

## Outputs
- `test_comprehension/business_scenarios.json` (older projects: `comprehension/`)
- `test_comprehension/business_scenarios.md`
- `test_comprehension/requirements.json` — only with `requirements.enabled` (Phase 1)
- Writes through an `ArtifactRegistry` for the project directory (persists artifact provenance)

## Failure mode

Per-document `ValueError` from `extract_requirements` is caught and logged per document/module — one
bad document doesn't abort the whole batch. No tiered `execute_with_fallback` routing at this
agent's own level (unlike `TestDataAgent`/`ScriptGenerationAgent`) — `DiscoveryAgent` is the one that
implements the LLM → NS → DOM-synthesis fallback chain around this agent, not `ComprehensionAgent`
itself.

## Fallback stub (`ComprehensionAgentStub`)

`agent.py` also defines `ComprehensionAgentStub`, the `python_stub` tier for the `comprehension` step in
`workflows/agent_registry.yaml` (disabled by default). It makes no LLM/HTTP call and writes nothing: it
returns `status: success`, `stub: true`, `scenarios_count: 0` so the run completes with the gap visible.
It is not registered in `agents/registry_setup.py` — the orchestrator imports it from the YAML entry.

## Requirements & traceability (Phase 1, `requirements.enabled`)

Off by default (`project.yaml` → `requirements.enabled: true` to opt in). When on, before scenario generation:

1. `tools.requirements.service.extract_for_module()` runs the shared extraction pipeline on the module's BRD
   text (`tools/requirements/extract.py`): criteria the document declares (`REQ-01` / `AC-01.2`) are parsed
   deterministically and kept with their own ids and exact quotes; **one** LLM call classifies them
   (testability + reason, P0–P3, risk tags), splits compound ones into atomic children (`AC-03.2.1`) and adds
   undeclared ones. Every quote is verified (`BrdIndex`); unverifiable additions are rejected and listed, and a
   criterion another module already holds is not re-added. The LLM can add criteria, never drop declared ones.
   Result: a per-module upsert into `test_comprehension/requirements.json`.
2. The scenario prompt gets the module's leaf ACs — plus the criteria its BRD also states but another module
   already holds (shared BRD sections are de-duplicated at extraction) — and returns `ac_ids` per scenario.
3. `link_scenario_models()` keeps only known ids (a split parent expands to its children) and backfills
   unlinked scenarios by word-overlap similarity (`ac_link_source: llm | similarity`).
4. After the final export, every scenario of the project that is still unlinked is re-linked project-wide
   (`relink_project_scenarios(only_unlinked=True)`): a scenario generated before a later module's criteria
   existed gets a second chance. Existing links are never changed.

A BRD that MTA synthesised from the DOM (URL-only discovery) yields `source: dom_inferred` criteria
(confidence ≤ 0.6). Any failure here is logged and reported under `result["requirements"][<module>]`
(`status: failed`); scenario generation then proceeds exactly as without the feature. With the flag off the
prompts, `business_scenarios.json` and the result are byte-for-byte what they were before Phase 1.
