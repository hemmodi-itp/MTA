"""
config.py — coverage profile and budget (Phase 3.5).

    test_generation:
      profile: standard            # smoke | standard | thorough | exhaustive  (absent → test design off)
      budget: { max_tests: 400, max_runtime_minutes: 45 }
      design_llm: true             # false → deterministic cases only (no decision tables / domain cases)
      # legacy caps (max_negative_cases / max_boundary_cases / max_data_iterations) are still honoured by the
      # legacy path; with a profile they no longer limit design cases and are logged as deprecated.

Per-module `modules[].test_generation` overrides apply on top (same merge order as tools/config/
test_generation_config.py). PROJECTS_BASE is read at call time so tests can redirect it.
"""

import os
from typing import Any, Dict, List, Optional

import yaml

from tools import constants
from tools.test_design.models import LEVELS

DEFAULT_BUDGET = {"max_tests": 400, "max_runtime_minutes": 45.0}
LEGACY_CAP_KEYS = ("max_negative_cases", "max_boundary_cases")   # max_data_iterations still feeds TestData


def _read_yaml(safe_project: str) -> dict:
    path = os.path.join(constants.PROJECTS_BASE, safe_project, "project.yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return {}


def resolve_design_config(raw: Optional[dict], module_id: Optional[str] = None) -> Dict[str, Any]:
    """project.yaml dict → {"enabled", "profile", "budget", "deprecated_caps"}. Never raises."""
    raw = raw or {}
    blocks = [raw.get("test_generation")]
    if module_id:
        for mod in raw.get("modules") or []:
            if isinstance(mod, dict) and mod.get("id") == module_id:
                blocks.append(mod.get("test_generation"))
    profile: Optional[str] = None
    budget = dict(DEFAULT_BUDGET)
    llm = True
    deprecated: List[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        p = str(block.get("profile") or "").strip().lower()
        if p in LEVELS:
            profile = p
        b = block.get("budget")
        if isinstance(b, dict):
            for key, cast in (("max_tests", int), ("max_runtime_minutes", float)):
                try:
                    if b.get(key) is not None and cast(b[key]) > 0:
                        budget[key] = cast(b[key])
                except (TypeError, ValueError):
                    pass
        deprecated += [k for k in LEGACY_CAP_KEYS if k in block]
        if "design_llm" in block:
            v = block["design_llm"]
            llm = v.strip().lower() in ("1", "true", "yes", "on") if isinstance(v, str) else bool(v)
    return {
        "enabled": profile is not None,
        "profile": profile or "standard",
        "budget": budget,
        "llm": llm,
        "deprecated_caps": sorted(set(deprecated)) if profile else [],
    }


def load_design_config(safe_project: str, module_id: Optional[str] = None) -> Dict[str, Any]:
    return resolve_design_config(_read_yaml(safe_project), module_id)


def design_enabled(safe_project: str, request: Optional[dict] = None) -> bool:
    """The request's resolved block wins (orchestrator runs); otherwise project.yaml is read."""
    block = (request or {}).get("test_design")
    if isinstance(block, dict) and "enabled" in block:
        return bool(block["enabled"])
    return load_design_config(safe_project)["enabled"]


def level_rank(level: str) -> int:
    return LEVELS.index(level)
