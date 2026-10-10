"""
base_url.py — the one place MTA resolves "which URL do the tests run against?".

Phase 0.6: there is NO default. The old silent `http://localhost:3000` fallback
pointed generated tests at whatever happened to listen there (often MTA's own
web app). Resolution order, first hit wins:

    explicit URL (request["url"], e.g. a --module narrow or project.url)
    -> project.url / legacy top-level url
    -> the module URL(s) of the targeted modules, when they agree on one URL
    -> the single distinct modules[].url of the project
    -> BaseUrlUnresolved (fail fast, with the candidates listed)
"""

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


class BaseUrlUnresolved(ValueError):
    """No base URL could be resolved — tests must not run against a guessed target."""


def module_urls(cfg: Dict[str, Any]) -> Dict[str, str]:
    """{module_id: url} for every module in a raw project.yaml dict (or a flat manifest)."""
    out: Dict[str, str] = {}
    for mod in (cfg or {}).get("modules") or []:
        if isinstance(mod, dict) and mod.get("id") and isinstance(mod.get("url"), str) and mod["url"].strip():
            out[str(mod["id"])] = mod["url"].strip()
    return out


def _project_url(cfg: Dict[str, Any]) -> str:
    project = (cfg or {}).get("project")
    if isinstance(project, dict) and isinstance(project.get("url"), str) and project["url"].strip():
        return project["url"].strip()
    top = (cfg or {}).get("url")  # legacy flat manifests
    return top.strip() if isinstance(top, str) and top.strip() else ""


def resolve_project_base_url(cfg: Dict[str, Any]) -> str:
    """project.url, else the single distinct module URL, else "" (ambiguous or none)."""
    url = _project_url(cfg)
    if url:
        return url
    distinct = sorted(set(module_urls(cfg).values()))
    return distinct[0] if len(distinct) == 1 else ""


def resolve_execution_base_url(
    explicit_url: Optional[str],
    cfg: Dict[str, Any],
    target_modules: Iterable[str] = (),
) -> Tuple[str, str]:
    """
    Returns (url, source) or raises BaseUrlUnresolved.

    *cfg* may be the raw project.yaml dict or the flat manifest request (both carry
    `modules`). *target_modules* are the module ids of the specs about to run.
    """
    if isinstance(explicit_url, str) and explicit_url.strip():
        return explicit_url.strip(), "request"
    url = _project_url(cfg)
    if url:
        return url, "project.url"
    by_module = module_urls(cfg)
    targets = [m for m in target_modules if m]
    if targets:
        wanted = sorted({by_module[m] for m in targets if m in by_module})
        if len(wanted) == 1:
            return wanted[0], "module.url"
    distinct = sorted(set(by_module.values()))
    if len(distinct) == 1:
        return distinct[0], "module.url"
    if not distinct:
        raise BaseUrlUnresolved(
            "base URL unresolved: project.yaml has no project.url and no modules[].url — "
            "set one (or BASE_URL). MTA no longer falls back to http://localhost:3000."
        )
    raise BaseUrlUnresolved(
        "base URL ambiguous: the targeted specs span modules with different URLs "
        f"{distinct} and no project.url is set — run with --module <id> or set project.url."
    )


def load_project_yaml(projects_base: str, project_name: str) -> Dict[str, Any]:
    path = os.path.join(projects_base, project_name, "project.yaml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def module_ids_of_targets(targets: Iterable[str]) -> List[str]:
    """Module ids from spec paths shaped like .../test_scripts/<module_id>/<file>.spec.ts."""
    ids: List[str] = []
    for t in targets:
        parts = str(t).replace("\\", "/").split("/")
        if "test_scripts" not in parts:
            continue
        i = parts.index("test_scripts")
        mid = parts[i + 1] if i + 1 < len(parts) else ""
        if mid and not mid.endswith(".ts") and mid not in ids:
            ids.append(mid)
    return ids
