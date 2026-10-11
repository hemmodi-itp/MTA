"""
service.py — project-level deep discovery: run once, reuse, write the five artifacts.

    ensure_app_discovery(project_name, request=None, force=False) -> summary dict

Runs only when project.yaml sets `discovery.deep: true` and the project is not an
interactive-scan project. Seeds = project.url + every module URL (audit A13: modular projects
run one module per process, so the crawl is project-wide, not per module). A fresh
app_map.json with the same config_hash (discovery block, roles, seeds, safety policy) that is
younger than `discovery.reuse_minutes` is reused unless *force* (`--force-recrawl`).

Never raises: callers (DiscoveryAgent, the CLI, the benchmark) get {"status": "failed", ...}.
"""

import datetime as _dt
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from tools.discovery.deep.config import DiscoveryConfig, config_hash, load_config, load_roles

_log = logging.getLogger("workflow.discovery.deep")

ARTIFACTS = ("app_map", "form_model", "api_inventory", "permission_matrix", "baseline")
COMPREHENSION_DIR = "test_comprehension"


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"


def project_dir(project_name: str) -> str:
    from tools import constants
    return os.path.join(constants.PROJECTS_BASE, _safe_name(project_name))


def artifact_paths(project_name: str) -> Dict[str, str]:
    base = os.path.join(project_dir(project_name), COMPREHENSION_DIR)
    return {name: os.path.join(base, f"{name}.json") for name in ARTIFACTS}


def build_seeds(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    seeds: List[Dict[str, Any]] = []
    seen = set()

    def add(url: Optional[str], module_id: Optional[str], setup: Optional[list]) -> None:
        if not url or not isinstance(url, str) or "://" not in url or url in seen:
            return
        seen.add(url)
        seeds.append({"url": url, "module_id": module_id, "setup_steps": list(setup or [])})

    add(manifest.get("url"), None, None)
    for m in manifest.get("modules") or []:
        if isinstance(m, dict):
            add(m.get("url"), m.get("id"), m.get("setup"))
    return seeds


def _age_minutes(generated_at: Optional[str]) -> Optional[float]:
    if not generated_at:
        return None
    try:
        ts = _dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds() / 60


def _reusable(paths: Dict[str, str], h: str, cfg: DiscoveryConfig) -> bool:
    if not all(os.path.exists(p) for p in paths.values()):
        return False
    try:
        with open(paths["app_map"], encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return False
    age = _age_minutes(doc.get("generated_at"))
    return doc.get("config_hash") == h and age is not None and age < cfg.reuse_minutes


def summarise(docs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    app_map = docs.get("app_map") or {}
    forms = (docs.get("form_model") or {}).get("forms") or []
    return {
        "states": len(app_map.get("states") or []),
        "page_templates": len({s["url_template"] for s in app_map.get("states") or [] if s.get("kind") == "page"}),
        "transitions": len(app_map.get("transitions") or []),
        "forms": len(forms),
        "probes": sum(len(f.get("probes") or []) for f in forms),
        "endpoints": len((docs.get("api_inventory") or {}).get("endpoints") or []),
        "roles": [r.get("name") for r in app_map.get("roles") or []],
        "stopped_by": app_map.get("stopped_by") or {},
        "duration_s": app_map.get("duration_s"),
    }


def ensure_app_discovery(project_name: str, request: Optional[Dict[str, Any]] = None, force: bool = False,
                         log: Optional[Callable[[str], None]] = None,
                         discovery_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    log = log or (lambda m: _log.info(m))
    try:
        from tools.project_manifest import load_project_manifest
        from tools.safety.policy import SafetyPolicy
        from tools.discovery.deep.roles import default_role

        manifest = load_project_manifest(project_name)
        request = request or {}
        block = dict(manifest.get("discovery") or request.get("discovery") or {})
        for k, v in (discovery_overrides or {}).items():
            block[k] = {**(block.get(k) or {}), **v} if isinstance(v, dict) else v
        cfg = load_config(block)
        if not cfg.deep:
            return {"status": "disabled"}
        if manifest.get("interactive_scan"):
            return {"status": "skipped", "reason": "interactive_scan projects are recorded by a human (--record)"}
        seeds = build_seeds(manifest)
        if not seeds:
            return {"status": "skipped", "reason": "no URL in project.yaml"}
        policy = SafetyPolicy.from_request(manifest.get("safety"))
        auth_req = {k: request.get(k) for k in ("auth_storage_state", "auth_config") if request.get(k)}
        roles = load_roles(manifest.get("auth_roles")) or [default_role(auth_req)]
        h = config_hash(cfg, roles, [s["url"] for s in seeds], manifest.get("safety") or {})
        paths = artifact_paths(project_name)
        if not force and _reusable(paths, h, cfg):
            with open(paths["app_map"], encoding="utf-8") as f:
                summary = summarise({"app_map": json.load(f)})
            log(f"[deep] reusing app_map.json (same config, younger than {cfg.reuse_minutes:g} min)")
            return {"status": "reused", "paths": paths, **summary}

        from tools.discovery.deep.crawl import DeepDiscovery
        log(f"[deep] crawling {len(seeds)} seed(s) as {len(roles)} role(s): {', '.join(r.name for r in roles)}")
        started = time.monotonic()
        docs = DeepDiscovery(project_name, cfg, roles, seeds, policy,
                             browser=manifest.get("browser") or "chromium",
                             headless=bool(manifest.get("headless", True)), log=log, config_hash=h).run()
        from contracts.artifacts import save_artifact
        os.makedirs(os.path.dirname(paths["app_map"]), exist_ok=True)
        for name in ARTIFACTS:
            save_artifact(name, paths[name], docs[name])
        summary = summarise(docs)
        log(f"[deep] done in {time.monotonic() - started:.1f}s — {summary['states']} state(s), "
            f"{summary['forms']} form(s), {summary['probes']} probe(s), {summary['endpoints']} endpoint(s)")
        return {"status": "success", "paths": paths, **summary}
    except Exception as exc:  # never break discovery
        _log.exception("[deep] deep discovery failed")
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]}
