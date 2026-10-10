"""
config.py — the `requirements:` block of project.yaml (Phase 1).

    requirements:
      enabled: false          # master switch: requirements.json, scenario ac_ids, test-case ids,
                              # Playwright tags/annotations, traceability.json, report section
      doc_id_patterns:        # optional regexes with named groups `id` and `text`
        requirement: '…'
        criterion: '…'

Default is off (plan principle 4: opt-in per project until validated on the benchmark). Agents that receive the
flattened manifest read `request["requirements"]`; agents that read project.yaml directly use
load_requirements_config(). PROJECTS_BASE is read at call time (tests redirect it).
"""

import os
import re
from typing import Any, Dict, Optional

import yaml

from tools import constants

DEFAULTS: Dict[str, Any] = {"enabled": False, "doc_id_patterns": {}}


def resolve_requirements_config(raw: Optional[dict]) -> Dict[str, Any]:
    """project.yaml dict → normalised {"enabled": bool, "doc_id_patterns": {...}}. Never raises."""
    block = (raw or {}).get("requirements")
    block = block if isinstance(block, dict) else {}
    enabled = block.get("enabled", DEFAULTS["enabled"])
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
    patterns = block.get("doc_id_patterns") if isinstance(block.get("doc_id_patterns"), dict) else {}
    valid = {}
    for key in ("requirement", "criterion"):
        rx = patterns.get(key)
        if not rx:
            continue
        try:
            compiled = re.compile(str(rx))
        except re.error:
            continue
        if {"id", "text"} <= set(compiled.groupindex):
            valid[key] = str(rx)
    return {"enabled": bool(enabled), "doc_id_patterns": valid}


def project_dir(safe_project: str) -> str:
    return os.path.join(constants.PROJECTS_BASE, safe_project)


def load_requirements_config(safe_project: str) -> Dict[str, Any]:
    path = os.path.join(project_dir(safe_project), "project.yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    return resolve_requirements_config(raw)


def requirements_enabled(safe_project: str, request: Optional[dict] = None) -> bool:
    """The request's resolved block wins (orchestrator runs); otherwise project.yaml is read."""
    block = (request or {}).get("requirements")
    if isinstance(block, dict) and "enabled" in block:
        return bool(block["enabled"])
    return load_requirements_config(safe_project)["enabled"]
