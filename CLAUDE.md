# agentic-qa-platform — Agent Structure Mandate

This is an org-level mandate for everything under `agents/`. It exists because agents used to share
folders (`agents/discovery/` held both `DiscoveryAgent` and `ComprehensionAgent`; `agents/test_creation/`
held three agents; `agents/test_execution/` held five) with shared `agent.md`/`skills.py`/`prompt.py`
files across siblings, making it unclear which file belonged to which agent. Every agent now lives in
its own dedicated folder.

## The mandate

**Every agent gets its own folder. No agent folder is ever shared by more than one agent's files.**

### Categories (fixed, closed set — do not add a 6th without updating this file)

| Category folder | What belongs here |
|---|---|
| `agents/comprehension/` | Requirement/BRD ingestion and DOM/UI discovery agents |
| `agents/test_creation/` | Test-artifact generation agents (test data, semantic mapping, script generation, dedup, BDD, etc.) |
| `agents/test_execution/` | Test-run and result-handling agents (execution, healing, reporting, locator resolution) |
| `agents/evaluation/` | Verdict and scoring agents of the BRD-compliance pipeline: requirement traceability, repository review, compliance scoring (added for the MTA redesign) |
| `agents/orchestrator/` | The single workflow-dispatch driver — no sub-agents, kept flat since it's already 1:1 |

### Required files — every agent folder, no exceptions

```
agents/<category>/<agent_name>/
├── __init__.py     (empty)
├── agent.py         ← the ONLY acceptable main-file name. Never <name>_agent.py or agent_<name>.py.
├── agent.md         (prose spec: inputs, outputs, behavior, failure modes)
├── agent.json        (machine-readable manifest — see schema below)
├── prompt.py         (LLM prompt constant(s), or a stub — see below)
├── server.py         (standalone CLI runner, or a stub)
├── skills.py         (AgentSkill entries, or a stub)
└── tools.py          (re-exported tool functions, or a stub)
```

If a file doesn't apply to a given agent, it must still exist, as an explicit stub — never omitted:

```python
"""
prompt.py — not used.
<AgentName> makes no LLM calls (pure Python / subprocess / browser automation).
"""
# Not used — <AgentName> is a pure-Python agent with no LLM calls.
```

The `# Not used — ...` line is the grep-able marker — it's how a future lint pass can tell "deliberately
inapplicable" apart from "someone forgot this file." Match this wording pattern for any new stub.

`skills.py`'s stub keeps `SKILLS: dict = {}` (not comment-only) so `from agents.X.skills import SKILLS`
works uniformly across every agent.

### `agent.json` schema

```jsonc
{
  "name": "string",              // class name, e.g. "DiscoveryAgent"
  "registry_key": "string|null", // key in registry_setup.py; null if unregistered (Orchestrator)
  "category": "string",          // comprehension | test_creation | test_execution | evaluation | orchestrator
  "module_path": "string",       // dotted import path to agent.py
  "version": "string",
  "status": "active|stub",
  "base_class": "BaseAgent|none",
  "llm_calls": "boolean",
  "description": "string",
  "inputs": [{ "name": "string", "type": "string", "required": "boolean", "description": "string" }],
  "outputs": [{ "name": "string", "type": "string", "description": "string" }],
  "dependencies": ["string"],    // other agent class names this one directly invokes
  "skills": ["string"],          // keys present in this folder's skills.py SKILLS dict
  "doc": "agent.md"
}
```
Fill every field for real — it's machine-read, so nothing here should be a stub or placeholder.

## Creating a new agent

**New agents MUST be created via the scaffold script — do not hand-create agent folders:**

```
python tools/scaffold_agent.py --name <agent_name> --category <comprehension|test_creation|test_execution|evaluation|orchestrator> \
    [--has-llm] [--has-tools] [--has-server] [--dry-run]
```

This generates all 7 files with correct stub/real content based on the flags. It deliberately does
**not** touch `agents/registry_setup.py` or the `workflows/*.yaml` files — it prints a "next steps"
checklist instead, since wiring a new agent into the orchestrator has real side effects (registry key
naming, workflow step ordering) that shouldn't be automated silently.

## Live reference example

`agents/test_creation/dedup/` — small, single-file-per-concern, every template file present and
correctly filled. Use it as the template to compare a new agent folder against.

## Import-path notes

- Cross-agent imports (e.g. `ExecutionAgent` importing `UIExecutionAgent`) must use the full new
  dotted path: `from agents.test_execution.ui_execution.agent import UIExecutionAgent`.
- Dynamic imports driven by YAML `fallback_module` strings in `workflows/agent_registry.yaml` are a
  second place path correctness matters, separate from static imports — they're resolved via
  `importlib.import_module` at runtime and won't show up in a static import grep.
- `agents/registry_setup.py` is the hub — every registered agent's constructor is imported there.
  Check it first when tracing whether an agent is wired into the default workflow.
