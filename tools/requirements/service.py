"""
service.py — project-level operations on requirements, shared by ComprehensionAgent, DiscoveryAgent and the
`python -m tools.requirements.build` CLI (Phase 1.1).

  extract_for_module()     extract one module's BRD and upsert it into requirements.json
  criteria_for_prompt()    the module's leaf criteria as [{id, statement}] for the scenario prompt
  link_scenario_models()   validate / backfill ac_ids on BusinessScenario objects
  relink_project_scenarios()  re-link business_scenarios.json on disk (existing projects, cached discovery)
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from contracts.artifacts.io import load_payload, save_artifact
from contracts.artifacts.paths import artifact_path
from tools.requirements.config import load_requirements_config, project_dir
from tools.requirements.extract import ExtractionResult, extract_requirements
from tools.requirements.ids import IdAllocator
from tools.requirements.linking import link_scenario
from tools.requirements.models import RequirementsDoc
from tools.requirements.store import load_requirements, reserved_ids, upsert_module
from tools.state.artifact_registry import ArtifactRegistry

SYNTHETIC_BRD_NAME = "synthetic_brd.md"


def extract_for_module(safe_project: str, text: str, llm, module_id: Optional[str] = None,
                       module_label: str = "", brd_file: Optional[str] = None, source: str = "brd",
                       logger=None) -> Tuple[RequirementsDoc, ExtractionResult]:
    cfg = load_requirements_config(safe_project)
    existing = load_requirements(safe_project)
    allocator = IdAllocator(ArtifactRegistry(project_dir(safe_project)))
    result = extract_requirements(
        text, llm, allocator=allocator, module_id=module_id, module_label=module_label, source=source,
        patterns=cfg.get("doc_id_patterns") or None, reserved=reserved_ids(existing, module_id), logger=logger)
    allocator.save()
    doc = upsert_module(safe_project, module_id, result, brd_file=brd_file)
    if logger:
        n = sum(len(r.acceptance_criteria) for r in result.requirements)
        logger.info(f"[requirements] {module_id or 'project'}: {len(result.requirements)} requirement(s), "
                    f"{n} criteria, {len(result.rejected)} rejected, status={result.status}")
    return doc, result


def criteria_for_prompt(doc: Optional[RequirementsDoc], module_id: Optional[str] = None) -> List[Dict[str, str]]:
    """The module's leaf criteria, plus criteria its BRD also states but another module already holds
    (shared BRD sections are de-duplicated at extraction, yet this module's scenarios may exercise them)."""
    if doc is None:
        return []
    leaves = doc.leaf_criteria(module_id) if module_id else doc.leaf_criteria()
    if module_id:
        index = {ac.id: ac for ac in doc.criteria()}
        shared = [w.id for w in doc.warnings
                  if w.module_id == module_id and w.kind == "duplicate_of_other_module" and w.id in index]
        have = {ac.id for ac in leaves}
        for ac_id in dict.fromkeys(shared):
            for leaf in index[ac_id].children or [ac_id]:
                if leaf not in have and leaf in index:
                    leaves.append(index[leaf])
                    have.add(leaf)
    return [{"id": ac.id, "statement": ac.statement} for ac in leaves]


def link_scenario_models(scenarios: List[Any], doc: Optional[RequirementsDoc],
                         module_id: Optional[str] = None) -> List[Any]:
    """BusinessScenario objects → new objects with validated / backfilled ac_ids."""
    if doc is None or not doc.requirements or not scenarios:
        return scenarios
    cls = type(scenarios[0])
    return [cls.model_validate(link_scenario(s.model_dump(), doc, module_id)) for s in scenarios]


def relink_project_scenarios(safe_project: str, doc: Optional[RequirementsDoc] = None,
                             only_unlinked: bool = False) -> int:
    """Re-link scenarios in business_scenarios.json; returns how many now carry ac_ids.

    only_unlinked: leave scenarios that already have links alone — used after each module's comprehension so a
    scenario linked before a later module's criteria existed gets a second, project-wide chance."""
    doc = doc or load_requirements(safe_project)
    path = artifact_path(project_dir(safe_project), "business_scenarios", existing_only=True)
    if doc is None or not path:
        return 0
    payload = load_payload("business_scenarios", path)
    scenarios = payload.get("scenarios") or []
    linked = [link_scenario(sc, doc) if isinstance(sc, dict) and not (only_unlinked and sc.get("ac_ids")) else sc
              for sc in scenarios]
    payload["scenarios"] = linked
    save_artifact("business_scenarios", path, payload)
    return sum(1 for sc in linked if isinstance(sc, dict) and sc.get("ac_ids"))


def document_source(documents: List[Any], request: Optional[dict] = None) -> str:
    """'dom_inferred' when comprehension runs on the BRD MTA synthesised from the DOM (URL-only mode)."""
    if (request or {}).get("requirements_source") == "dom_inferred":
        return "dom_inferred"
    names = {os.path.basename(getattr(d, "file_name", "") or "") for d in documents}
    return "dom_inferred" if SYNTHETIC_BRD_NAME in names else "brd"
