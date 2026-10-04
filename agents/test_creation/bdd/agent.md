# BDDAgent

Placeholder for future BDD (Gherkin `.feature` file) test-artifact generation.

## Status

**Stub.** `execute()` currently returns a static result without doing any real work:

```python
{"module": "bdd", "status": "stub"}
```

No BDD scenario generation, no `.feature` file writing, no Gherkin parsing exists yet.

## Contract (once implemented)

| | |
|---|---|
| Input | `project_name: str` |
| Output | `{module: "bdd", status: "stub"}` — placeholder only |

Registered as `"bdd"` in `agents/registry_setup.py`, disabled by default
(`workflows/agents.yaml`: `bdd: enabled: false`) and not referenced by any step in
`workflows/full_workflow.yaml` — this agent does not currently run in any real workflow.

## Intended future scope

Generate Gherkin `.feature` files from business scenarios (`comprehension/business_scenarios.json`),
as an alternative or complement to the TypeScript `.spec.ts` output of `ScriptGenerationAgent`.
