"""
tools/scaffold_agent.py -- generates a compliant agent folder skeleton.

Enforces the org-standard per-agent template documented in CLAUDE.md: every
agent gets its own folder under one of the 4 fixed category folders, with
all 7 template files present (real content or an explicit "not used" stub).

Usage:
    python tools/scaffold_agent.py --name my_agent --category test_creation
    python tools/scaffold_agent.py --name my_agent --category test_execution --has-llm --has-tools
    python tools/scaffold_agent.py --name my_agent --category comprehension --dry-run

Deliberately does NOT touch agents/registry_setup.py or workflows/*.yaml --
wiring a new agent into the orchestrator has real side effects (registry key
naming, workflow step ordering) that shouldn't be automated silently. Prints
a "next steps" checklist instead.
"""

import argparse
import json as _json
import os
import re
import sys
from typing import Optional

_CATEGORIES = ("comprehension", "test_creation", "test_execution", "evaluation", "orchestrator")


def _class_name(agent_name: str) -> str:
    return "".join(part.capitalize() for part in agent_name.split("_")) + "Agent"


def _stub(kind: str, class_name: str, reason: str) -> str:
    return (
        f'"""\n'
        f"{kind} — not used.\n\n"
        f"{class_name} {reason}\n"
        f'"""\n\n'
        f"# Not used — {class_name} {reason}\n"
    )


def _skills_stub(class_name: str) -> str:
    return (
        f'"""\n'
        f"skills.py — not used.\n\n"
        f"{class_name} is invoked directly by the orchestrator via\n"
        f"execute(request, state); it is not exposed through a skill-selection\n"
        f"interface. This stub exists only to satisfy the org-standard\n"
        f"per-agent file template.\n"
        f'"""\n\n'
        f"SKILLS: dict = {{}}\n"
        f"# Not used — {class_name} has no AgentSkill entries.\n"
    )


def _agent_py(class_name: str, name: str, has_llm: bool) -> str:
    return (
        f'"""\n'
        f"{class_name} — TODO: describe what this agent does.\n"
        f'"""\n\n'
        f"from typing import Any, Dict, Optional\n\n"
        f"from agents.base_agent import BaseAgent\n"
        f"from tools.shared import get_logger\n\n\n"
        f"class {class_name}(BaseAgent):\n"
        f"    def __init__(self, settings: Optional[dict] = None):\n"
        f"        self.settings = settings or {{}}\n"
        f'        self.logger = get_logger("agent.{name}")\n\n'
        f"    def execute(self, request: dict, state: dict) -> Dict[str, Any]:\n"
        f"        # TODO({name}): implement\n"
        f"        raise NotImplementedError(\"{class_name}.execute is not implemented yet\")\n"
    )


def _agent_md(class_name: str) -> str:
    return (
        f"# {class_name}\n\n"
        f"TODO: describe what this agent does.\n\n"
        f"## Inputs\n- TODO\n\n"
        f"## Outputs\n- TODO\n\n"
        f"## Failure mode\n- TODO\n"
    )


def _agent_json(class_name: str, name: str, category: str, registry_key: Optional[str], has_llm: bool) -> str:
    payload = {
        "name": class_name,
        "registry_key": registry_key,
        "category": category,
        "module_path": f"agents.{category}.{name}.agent",
        "version": "0.1.0",
        "status": "stub",
        "base_class": "BaseAgent",
        "llm_calls": has_llm,
        "description": "TODO",
        "inputs": [],
        "outputs": [],
        "dependencies": [],
        "skills": [],
        "doc": "agent.md",
    }
    return _json.dumps(payload, indent=2) + "\n"


def _server_stub(class_name: str) -> str:
    return (
        f'"""\n'
        f"server.py — not used.\n\n"
        f"{class_name} has no standalone CLI entry point; it is invoked only\n"
        f"through AgentRegistry / OrchestratorAgent. See\n"
        f"agents/test_creation/artifact_generator/server.py for the pattern to\n"
        f"follow if a standalone runner is ever added.\n"
        f'"""\n\n'
        f"# Not used — no standalone runner needed; invoked via AgentRegistry.\n"
    )


def _tools_stub(class_name: str) -> str:
    return (
        f'"""\n'
        f"tools.py — not used.\n\n"
        f"{class_name} has no externally-reusable tool functions to re-export;\n"
        f"all logic lives inline in agent.py.\n"
        f'"""\n\n'
        f"# Not used — {class_name} has no dedicated tools/ package to re-export.\n"
    )


def _prompt_stub_or_real(class_name: str, has_llm: bool) -> str:
    if not has_llm:
        return _stub("prompt.py", class_name, "makes no LLM calls.")
    # Established convention drops the "Agent" suffix (HealingAgent -> HEAL_PROMPT,
    # SemanticMapAgent -> SEMANTIC_MAP_PROMPT), not <CLASS_NAME>_AGENT_PROMPT.
    base = re.sub(r"Agent$", "", class_name) or class_name
    prompt_const = re.sub(r"(?<!^)(?=[A-Z])", "_", base).upper() + "_PROMPT"
    return (
        f'"""prompt.py — LLM prompt template for {class_name}."""\n\n'
        f"from string import Template\n\n"
        f'{prompt_const} = Template("""\n'
        f"TODO: write the prompt for {class_name}.\n"
        f'""")\n'
    )


def build_agent_folder(name: str, category: str, has_llm: bool, has_tools: bool, has_server: bool,
                        force: bool = False, dry_run: bool = False) -> str:
    if category not in _CATEGORIES:
        raise ValueError(f"--category must be one of {_CATEGORIES}, got '{category}'")
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        raise ValueError(f"--name must be snake_case, got '{name}'")

    class_name = _class_name(name)
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents", category, name)
    base_dir = os.path.normpath(base_dir)

    if os.path.exists(base_dir) and not force:
        raise FileExistsError(f"'{base_dir}' already exists — pass --force to overwrite")

    files = {
        "__init__.py": "",
        "agent.py": _agent_py(class_name, name, has_llm),
        "agent.md": _agent_md(class_name),
        "agent.json": _agent_json(class_name, name, category, None, has_llm),
        "prompt.py": _prompt_stub_or_real(class_name, has_llm),
        "server.py": (
            _server_stub(class_name) if not has_server else
            f'"""server.py — standalone runner for {class_name}. See\n'
            f'agents/test_creation/artifact_generator/server.py for the pattern.\n"""\n\n'
            f"# TODO: implement a standalone CLI runner, following the pattern in\n"
            f"# agents/test_creation/artifact_generator/server.py\n"
        ),
        "skills.py": (
            _skills_stub(class_name) if not has_tools else
            f'"""skills.py — AgentSkill entries for {class_name}."""\n\n'
            f"from tools.shared.skill_model import AgentSkill\n\n"
            f"SKILLS = {{\n"
            f'    # TODO: define skill entries, e.g.:\n'
            f'    # "{name}": AgentSkill(name="...", description="...", strengths=[...]),\n'
            f"}}\n"
        ),
        "tools.py": (
            _tools_stub(class_name) if not has_tools else
            f'"""tools.py — tool surface for {class_name}."""\n\n'
            f"# TODO: re-export this agent's tool functions here, e.g.:\n"
            f"# from tools.{category}.{name} import some_function\n"
        ),
    }

    if dry_run:
        print(f"Would create: {base_dir}/")
        for fname in files:
            print(f"  {fname}")
        return base_dir

    os.makedirs(base_dir, exist_ok=True)
    for fname, content in files.items():
        with open(os.path.join(base_dir, fname), "w", encoding="utf-8") as f:
            f.write(content)

    return base_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new agent folder per the org-standard template")
    parser.add_argument("--name", required=True, help="Agent name, snake_case (e.g. my_agent)")
    parser.add_argument("--category", required=True, choices=_CATEGORIES)
    parser.add_argument("--has-llm", action="store_true", help="Generate a real prompt.py template instead of a stub")
    parser.add_argument("--has-tools", action="store_true", help="Generate real tools.py/skills.py templates instead of stubs")
    parser.add_argument("--has-server", action="store_true", help="Generate a real server.py template instead of a stub")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing folder")
    parser.add_argument("--dry-run", action="store_true", help="Print the file tree without writing anything")
    args = parser.parse_args()

    try:
        base_dir = build_agent_folder(
            args.name, args.category, args.has_llm, args.has_tools, args.has_server,
            force=args.force, dry_run=args.dry_run,
        )
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        return 0

    class_name = _class_name(args.name)
    print(f"Created: {base_dir}/")
    print()
    print("Next steps (not done automatically):")
    print(f"  1. Implement {class_name}.execute() in agent.py")
    print(f"  2. Fill in agent.md and agent.json's description/inputs/outputs")
    print(f"  3. Register it (lazily) in agents/registry_setup.py — add to MTA_AGENTS or LEGACY_AGENTS:")
    print(f'       ("{args.name}", "agents.{args.category}.{args.name}.agent", "{class_name}", {{}}),')
    print(f"  4. If it should run in the default pipeline, add a step entry to")
    print(f"     workflows/full_workflow.yaml and an enabled flag in workflows/agents.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
