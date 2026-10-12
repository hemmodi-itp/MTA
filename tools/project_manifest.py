"""
project_manifest.py — shared project.yaml loading + module narrowing.

Single source of truth for "given a project name and an optional module id,
what URL/setup_steps/auth/interactive_scan flag apply" — used by both
OrchestratorAgent (the full pipeline) and main.py's --record command (which
runs outside the pipeline and needs the exact same resolution logic).
"""

import os
from typing import Optional

import yaml

from tools.constants import PROJECTS_BASE as _PROJECTS_DIR
from tools.discovery.deep.config import resolve_discovery_config, resolve_roles
from tools.requirements.config import resolve_requirements_config
from tools.safety.policy import SafetyPolicy, warn_if_unspecified
from tools.test_design.config import resolve_design_config


def load_project_manifest(project_name: str) -> dict:
    """Flatten application_assets/projects/{project}/project.yaml into a request dict."""
    manifest_path = os.path.join(_PROJECTS_DIR, project_name, "project.yaml")
    if not os.path.exists(manifest_path):
        return {}
    with open(manifest_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    flat: dict = {}
    flat["application_name"] = raw.get("project", {}).get("application_name", project_name)
    flat["url"] = raw.get("project", {}).get("url")
    flat["browser"] = raw.get("project", {}).get("browser", "chromium")
    flat["headless"] = raw.get("project", {}).get("headless", True)
    flat["brd_dir"] = raw.get("input", {}).get("brd_dir")
    flat["suite"] = raw.get("test_execution", {}).get("suite", project_name)
    flat["ns_base_url"] = raw.get("ns_config", {}).get("base_url")
    flat["discovery_timeout_s"] = raw.get("project", {}).get("discovery_timeout_s")
    flat["interactive_scan"] = raw.get("project", {}).get("interactive_scan", False)
    modules = raw.get("modules")
    if modules:
        flat["modules"] = modules
    auth = raw.get("auth")
    if auth and auth.get("enabled"):
        flat["auth"] = auth
    # Phase 0 safety rails — `environment:` + `safety:` (see tools/safety/policy.py).
    # Always present, so every agent sees the same resolved policy; a manifest
    # without `environment:` resolves to "unspecified" (gated like prod) + a warning.
    policy = SafetyPolicy.from_project_config(raw)
    warn_if_unspecified(policy, project_name)
    flat["environment"] = policy.environment
    flat["safety"] = policy.to_request()
    # Phase 0 artifact contracts — boundary-validation mode (warn | block).
    flat["contracts"] = resolve_contracts_config(raw)
    # Phase 1 requirements & traceability — opt-in (`requirements.enabled`, default false).
    flat["requirements"] = resolve_requirements_config(raw)
    # Phase 2 deep discovery — opt-in (`discovery.deep`, default false) + `auth.roles`
    # (read even when auth.enabled is false; see tools/discovery/deep/config.py).
    flat["discovery"] = resolve_discovery_config(raw)
    # Phase 3 test design — on when `test_generation.profile` is set (see tools/test_design/config.py).
    flat["test_design"] = resolve_design_config(raw)
    roles = resolve_roles(raw)
    if roles:
        flat["auth_roles"] = roles
    return {k: v for k, v in flat.items() if v is not None}


def resolve_contracts_config(raw: dict) -> dict:
    """project.yaml `contracts:` block -> {"enforce": "warn"|"block"} (default warn)."""
    block = raw.get("contracts") if isinstance(raw.get("contracts"), dict) else {}
    enforce = str(block.get("enforce", "warn")).strip().lower()
    return {"enforce": enforce if enforce in ("warn", "block") else "warn"}


def narrow_to_module(flat: dict, module_filter: Optional[str], project_name: str) -> dict:
    """
    Narrow a flattened manifest to a single module's URL/setup_steps, the same
    way OrchestratorAgent.run() does for a normal pipeline run. Returns a new
    dict (does not mutate *flat*). No-op if module_filter is falsy or the
    manifest has no modules.
    """
    if not module_filter or not flat.get("modules"):
        return flat

    result = dict(flat)
    all_modules = result["modules"]
    matched = [m for m in all_modules if m.get("id") == module_filter]
    if not matched:
        available = [m.get("id") for m in all_modules]
        raise ValueError(
            f"Module '{module_filter}' not found in project '{project_name}'. "
            f"Available: {available}"
        )
    result["modules"] = matched
    module_url = matched[0].get("url")
    if module_url:
        result["url"] = module_url
    module_setup = matched[0].get("setup")
    if module_setup:
        result["setup_steps"] = module_setup
    return result
