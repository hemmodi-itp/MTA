# ComprehensionAgent

Reads BRD (requirement) documents and produces structured Business Scenarios via a five-step
pipeline:

```
parse_all_documents (or parse_document, per-module)
    → extract_requirements   (LLM, per document)
    → generate_business_scenarios  (LLM, combined)
    → validate_business_scenarios
    → export_scenarios
        → application_assets/projects/<project>/comprehension/
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
- `comprehension/business_scenarios.json`
- `comprehension/business_scenarios.md`
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
