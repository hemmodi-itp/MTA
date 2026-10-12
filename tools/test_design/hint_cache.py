"""
hint_cache.py — sanitised LLM hints per module (test_creation/test_design_llm_cache.json).

Keyed by a hash of the module's testable criteria: unchanged criteria → the cached hints are reused (no call), so
module-by-module runs (`main.py --module M0x`) keep every module's decision tables in the project-wide design, and
reruns cost nothing. A changed criterion invalidates that module's entry only.
"""

import hashlib
import json
import os
from typing import Any, Dict

from tools.test_design.inputs import DesignInputs

REL_PATH = os.path.join("test_creation", "test_design_llm_cache.json")


def criteria_hash(inp: DesignInputs, module_id: str) -> str:
    text = "\n".join(f"{a['id']}|{a['statement']}" for a in inp.testable_acs() if a["module_id"] == module_id)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load(project_dir: str) -> Dict[str, Any]:
    path = os.path.join(project_dir, REL_PATH)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(project_dir: str, cache: Dict[str, Any]) -> None:
    path = os.path.join(project_dir, REL_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(cache.items())), fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
