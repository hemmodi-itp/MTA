"""
test_generation_config — resolves the `test_generation:` block from a
project's project.yaml, with per-module overrides.

Defaults reflect "1 realistic positive flow, 1 negative case, 1 boundary
case, up to 3 data iterations for each" — exhaustive negative/boundary
matrices (8-10 variants, one test() each) were overwhelming real user-flow
coverage and slowing execution down without adding proportional value.
"""

import os
from typing import Optional

import yaml

from tools.constants import PROJECTS_BASE as _ASSETS_BASE

DEFAULT_TEST_GENERATION_CONFIG = {
    "max_negative_cases": 1,
    "max_boundary_cases": 1,
    "max_data_iterations": 3,
}


def load_test_generation_config(safe_project: str, module_id: Optional[str] = None) -> dict:
    """
    Resolve effective test_generation config for a project, with an optional
    per-module override.

    Merge order (later wins):
        hardcoded defaults
        -> project.yaml top-level `test_generation:`
        -> project.yaml modules[] entry matching module_id -> `test_generation:`

    Missing project.yaml, missing keys, or a module_id that doesn't match any
    module all fall back to the defaults for the missing pieces — this never
    raises.
    """
    config = dict(DEFAULT_TEST_GENERATION_CONFIG)

    yaml_path = os.path.join(_ASSETS_BASE, safe_project, "project.yaml")
    if not os.path.exists(yaml_path):
        return config

    try:
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return config

    _apply_overrides(config, cfg.get("test_generation"))

    if module_id:
        for mod in cfg.get("modules", []) or []:
            if mod.get("id") == module_id:
                _apply_overrides(config, mod.get("test_generation"))
                break

    return config


def _apply_overrides(config: dict, overrides: Optional[dict]) -> None:
    if not isinstance(overrides, dict):
        return
    for key in DEFAULT_TEST_GENERATION_CONFIG:
        if key in overrides:
            try:
                config[key] = int(overrides[key])
            except (TypeError, ValueError):
                continue
