"""
store.py — read and write test_comprehension/requirements.json (Phase 1.1).

The file is project-wide; comprehension runs module by module, so writes are a per-module upsert: a module's
previous requirements, rejections and warnings are replaced, other modules' entries are kept. Every write is
validated against RequirementsDoc and goes through contracts' atomic v2 writer.
"""

import os
from datetime import datetime, timezone
from typing import Dict, Optional

from contracts.artifacts.io import load_payload, save_artifact
from contracts.artifacts.paths import artifact_path
from tools.requirements.config import project_dir
from tools.requirements.extract import ExtractionResult
from tools.requirements.models import ModuleStatus, RequirementsDoc

FLAT_MODULE_KEY = "_project"     # modules-map key for a project without modules[]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def requirements_path(safe_project: str, existing_only: bool = False) -> Optional[str]:
    return artifact_path(project_dir(safe_project), "requirements", existing_only=existing_only)


def load_requirements(safe_project: str) -> Optional[RequirementsDoc]:
    path = requirements_path(safe_project, existing_only=True)
    if not path:
        return None
    return RequirementsDoc.model_validate(load_payload("requirements", path))


def reserved_ids(doc: Optional[RequirementsDoc], exclude_module: Optional[str]) -> Dict[str, str]:
    """Ids other modules already use → their title/statement (for cross-module collision detection)."""
    out: Dict[str, str] = {}
    for r in (doc.requirements if doc else []):
        if r.module_id == exclude_module:
            continue
        out[r.id] = r.title
        for ac in r.acceptance_criteria:
            out[ac.id] = ac.statement
    return out


def upsert_module(safe_project: str, module_id: Optional[str], result: ExtractionResult,
                  brd_file: Optional[str] = None) -> RequirementsDoc:
    doc = load_requirements(safe_project) or RequirementsDoc(project=safe_project)
    key = module_id or FLAT_MODULE_KEY
    keep = [r for r in doc.requirements if r.module_id != module_id]
    doc = RequirementsDoc.model_validate({
        **doc.model_dump(),
        "project": safe_project,
        "updated_at": _now(),
        "requirements": [r.model_dump() for r in keep + result.requirements],
        "rejected": [x.model_dump() for x in doc.rejected if x.module_id != module_id]
                    + [x.model_dump() for x in result.rejected],
        "warnings": [x.model_dump() for x in doc.warnings if x.module_id != module_id]
                    + [x.model_dump() for x in result.warnings],
        "modules": {**{k: v.model_dump() for k, v in doc.modules.items()},
                    key: ModuleStatus(brd_file=brd_file, status=result.status, limitations=result.limitations,
                                      extracted_at=_now()).model_dump()},
    })
    path = requirements_path(safe_project) or os.path.join(project_dir(safe_project), "test_comprehension",
                                                           "requirements.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_artifact("requirements", path, doc.model_dump(mode="json"))
    return doc
