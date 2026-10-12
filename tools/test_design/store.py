"""
store.py — read/write test_creation/test_cases.json and the per-scenario view ScriptGeneration uses.
"""

import json
import os
from typing import Any, Dict, List, Optional

from tools.test_design.models import TestCasesDoc

REL_PATH = os.path.join("test_creation", "test_cases.json")


def path_for(project_dir: str) -> str:
    return os.path.join(project_dir, REL_PATH)


def write_doc(project_dir: str, doc: Dict[str, Any]) -> str:
    TestCasesDoc.model_validate(doc)
    path = path_for(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def load_doc(project_dir: str) -> Optional[Dict[str, Any]]:
    path = path_for(project_dir)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cases_by_scenario(doc: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for c in (doc or {}).get("test_cases") or []:
        if c.get("scenario_id"):
            out.setdefault(c["scenario_id"], []).append(c)
    return out
