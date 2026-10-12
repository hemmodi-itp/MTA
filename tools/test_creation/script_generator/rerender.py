"""
rerender.py — rebuild a project's generated specs from test_plans.json, without an LLM (Phase 4.5 migration).

    python -m tools.test_creation.script_generator.rerender --project bench_buggy_shop [--check] [--spec M03_BS_001]

For every test_suite.json spec with generation_mode "action_library" and a stored plan, the spec is composed with
compose.compose_spec — the function ScriptGenerationAgent uses — under the project's current execution options
(test_steps, module_roles + modules[].role). The stored plan is not re-validated against today's action vocabulary:
a plan that still uses waitForTimeout renders (ActionEngine keeps it) and is reported.

--check prints a unified diff per spec and writes nothing. Otherwise each changed spec is written atomically and the
previous version is kept as <spec>.bak. Specs with no stored plan (tier-2 fallback, hand-written) are listed, never
touched. Exit code: 0 ok (with --check: 0 = no diff, 1 = a spec would change), 2 = project/inputs missing.
"""

import argparse
import difflib
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional

import yaml

from contracts.artifacts import load_payload
from tools import constants
from tools.base_url import resolve_project_base_url
from tools.execution.config import resolve_execution_config
from tools.test_creation.script_generator.compose import compose_spec, module_role_for


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _scenarios(path: str) -> Dict[str, dict]:
    raw = _load_json(path) or []
    if isinstance(raw, dict):
        raw = raw.get("scenarios", raw.get("business_scenarios", []))
    return {s.get("scenario_id"): s for s in raw if isinstance(s, dict) and s.get("scenario_id")}


def rerender_project(safe: str, *, check: bool = False, only: Optional[List[str]] = None,
                     projects_base: Optional[str] = None, out=print) -> Dict[str, Any]:
    base = projects_base or constants.PROJECTS_BASE
    pdir = os.path.join(base, safe)
    tc = os.path.join(pdir, "test_creation")
    yaml_path = os.path.join(pdir, "project.yaml")
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"project.yaml not found: {yaml_path}")
    with open(yaml_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    cfg = resolve_execution_config(raw)
    modules = {m["id"]: m for m in raw.get("modules") or [] if isinstance(m, dict) and m.get("id")}
    roles = list(((raw.get("auth") or {}).get("roles") or {}).keys())
    project_url = resolve_project_base_url(raw)
    suite = _load_json(os.path.join(tc, "test_suite.json")) or {}
    plans = load_payload("test_plans", os.path.join(tc, "test_plans.json"), {}) or {}
    scenarios = _scenarios(os.path.join(pdir, "test_comprehension", "business_scenarios.json"))
    flows = _load_json(os.path.join(tc, "flows.json")) or {}
    flows_meta = {name: f.get("params", []) for name, f in flows.items()}
    locator_map = _load_json(os.path.join(tc, "locator_map.json")) or {}

    summary: Dict[str, Any] = {"project": safe, "changed": [], "unchanged": [], "skipped": [], "warnings": []}
    for spec in suite.get("specs") or []:
        sid, rel = spec.get("spec_id"), spec.get("file")
        if only and sid not in only:
            continue
        plan = plans.get(sid)
        if spec.get("generation_mode") != "action_library" or not isinstance(plan, dict) or not plan.get("tests"):
            summary["skipped"].append({"spec_id": sid, "reason": "no stored action-library plan"})
            continue
        path = os.path.join(tc, "test_scripts", rel)
        if not os.path.exists(path):
            summary["skipped"].append({"spec_id": sid, "reason": f"spec file missing: {rel}"})
            continue
        module_id = spec.get("module_id") or rel.split("/")[0]
        module = modules.get(module_id) or {}
        scenario = scenarios.get(sid) or {"scenario_id": sid, "title": spec.get("scenario_title", sid)}
        sleeps = sum(1 for t in plan["tests"] for st in t.get("steps") or [] if st.get("action") == "waitForTimeout")
        if sleeps:
            summary["warnings"].append(f"{sid}: stored plan uses waitForTimeout {sleeps}x (rendered unchanged)")
        role = module_role_for(module.get("role"), cfg["module_roles"], roles, cfg["role_auth"],
                               warn=lambda m: summary["warnings"].append(f"{sid}: {m}"))
        content = compose_spec(
            plan, scenario, module.get("url") or project_url,
            os.path.join("projects", safe, "test_creation", "test_scripts", rel),
            project=safe, flows_meta=flows_meta, module_setup=module.get("setup"), role=role,
            test_steps=cfg["test_steps"], locator_map=locator_map,
        )
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
        if content == current:
            summary["unchanged"].append(sid)
            continue
        summary["changed"].append(sid)
        if check:
            out("".join(difflib.unified_diff(current.splitlines(True), content.splitlines(True),
                                             fromfile=f"a/{rel}", tofile=f"b/{rel}")))
            continue
        shutil.copyfile(path, path + ".bak")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        os.replace(tmp, path)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Re-render generated specs from test_plans.json (no LLM).")
    ap.add_argument("--project", required=True)
    ap.add_argument("--check", action="store_true", help="print the diff, write nothing")
    ap.add_argument("--spec", action="append", help="only this spec id (repeatable)")
    args = ap.parse_args(argv)
    try:
        summary = rerender_project(args.project, check=args.check, only=args.spec)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for w in summary["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    print(json.dumps({k: summary[k] for k in ("project", "changed", "unchanged", "skipped")}, indent=2))
    return 1 if (args.check and summary["changed"]) else 0


if __name__ == "__main__":
    sys.exit(main())
