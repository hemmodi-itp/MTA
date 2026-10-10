"""
build.py — build requirements.json for a project without running discovery (Phase 1, design R13).

    python -m tools.requirements.build --project X [--module M01] [--no-llm]

For each module (or the flat input directory) it parses the BRD, extracts requirements into
test_comprehension/requirements.json, re-links business_scenarios.json to the acceptance criteria, and rebuilds
traceability.json. Use it after turning `requirements.enabled` on for an existing project (cached discovery
skips comprehension), or to refresh requirements after editing a BRD.
"""

import argparse
import os
import sys
from typing import List, Optional

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_yaml(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _llm(no_llm: bool):
    if no_llm:
        return None
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    from connectors.connector_registry import ConnectorRegistry
    return ConnectorRegistry(_load_yaml(os.path.join(REPO_ROOT, "workflows", "settings.yaml"))).get_llm()


def build(project: str, module: Optional[str] = None, no_llm: bool = False, log=print) -> int:
    from tools.comprehension.parse_document import parse_all_documents, parse_document
    from tools.requirements.config import load_requirements_config, project_dir
    from tools.requirements.service import extract_for_module, relink_project_scenarios
    from tools.requirements.traceability import refresh_project

    pdir = project_dir(project)
    manifest = _load_yaml(os.path.join(pdir, "project.yaml"))
    if not manifest:
        log(f"error: {pdir}/project.yaml not found or empty")
        return 2
    if not load_requirements_config(project)["enabled"]:
        log("warning: requirements.enabled is off in project.yaml — requirements.json is built, but the "
            "pipeline will not use it until you turn the flag on.")
    input_dir = (manifest.get("input") or {}).get("brd_dir") or os.path.join(pdir, "inputs")
    llm = _llm(no_llm)

    modules: List[dict] = [m for m in manifest.get("modules") or [] if isinstance(m, dict) and m.get("id")]
    if module:
        modules = [m for m in modules if m["id"] == module]
        if not modules:
            log(f"error: module {module} is not declared in project.yaml")
            return 2
    jobs = []
    if modules:
        for m in modules:
            if m.get("brd_file") and os.path.exists(os.path.join(input_dir, m["brd_file"])):
                jobs.append((m["id"], f"{m['id']} {m.get('name', '')}".strip(), m["brd_file"],
                             [parse_document(os.path.join(input_dir, m["brd_file"]))]))
            else:
                log(f"skip {m['id']}: no BRD file ({m.get('brd_file') or 'brd_file not set'})")
    else:
        docs = parse_all_documents(input_dir)
        if docs:
            jobs.append((None, "", None, docs))

    if not jobs:
        log("error: no BRD documents found")
        return 1
    failed = 0
    for module_id, label, brd_file, docs in jobs:
        text = "\n\n".join(d.content for d in docs if getattr(d, "content", ""))
        _, res = extract_for_module(project, text, llm, module_id=module_id, module_label=label, brd_file=brd_file)
        n = sum(len(r.acceptance_criteria) for r in res.requirements)
        log(f"{module_id or 'project'}: {len(res.requirements)} requirement(s), {n} criteria, "
            f"{len(res.rejected)} rejected, status={res.status}")
        for lim in res.limitations:
            log(f"  - {lim}")
        failed += res.status == "failed"
    linked = relink_project_scenarios(project)
    log(f"business_scenarios.json: {linked} scenario(s) linked to acceptance criteria")
    trace = refresh_project(project, {"requirements": {"enabled": True}})
    if trace is not None:
        s = trace.summary
        log(f"traceability.json: {s['acs_covered']}/{s['acs_automatable']} automatable AC(s) covered, "
            f"{s['tests_unlinked']} unlinked test(s)")
    return 1 if failed == len(jobs) else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--module", default=None)
    ap.add_argument("--no-llm", action="store_true", help="declared criteria only, heuristic classification")
    args = ap.parse_args(argv)
    if os.getcwd() != REPO_ROOT:
        os.chdir(REPO_ROOT)     # PROJECTS_BASE is repo-relative
    return build(args.project, args.module, args.no_llm)


if __name__ == "__main__":
    sys.exit(main())
