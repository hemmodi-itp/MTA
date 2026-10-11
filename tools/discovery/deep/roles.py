"""
roles.py — open one browser context per role (task 2.6).

Strategies (auth.roles in project.yaml; read even when auth.enabled is false):
    anonymous     fresh context, no cookies
    storageState  context loaded from storage_state_path (skipped with a reason if missing)
    credentials   live login via tools/auth/live_login.perform_login (env-var credentials)
    setup         a module-style step list (goto / fill / click / wait), run on a fresh page

Without auth.roles there is one implicit role, `default`: the project's existing auth
(storageState file or live_login block); each seed module's own setup steps then run before
that seed is visited (see crawl.py).

Secrets never leave this module: artifacts only see {name, strategy}.
"""

import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from tools.discovery.deep.config import RoleConfig

_log = logging.getLogger("workflow.discovery.deep")

LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|auth)(/|$|\?)", re.I)


def default_role(request: Dict[str, Any]) -> RoleConfig:
    """The implicit single role when the project declares no auth.roles."""
    storage = request.get("auth_storage_state")
    live = request.get("auth_config") if (request.get("auth_config") or {}).get("strategy") == "live_login" else None
    if storage:
        return RoleConfig(name="default", strategy="storageState", storage_state_path=storage)
    if live:
        return RoleConfig(name="default", strategy="credentials", **{k: v for k, v in live.items()
                                                                     if k in RoleConfig.model_fields and k != "strategy"})
    return RoleConfig(name="default", strategy="anonymous")


def open_role(browser, role: RoleConfig, viewport: Optional[Dict[str, int]] = None) -> Tuple[Any, Any, Dict[str, Any]]:
    """-> (context, page, info). info = {ok, error?}. The caller closes the context."""
    ctx_kwargs: Dict[str, Any] = {}
    if viewport:
        ctx_kwargs["viewport"] = viewport
    if role.strategy == "storageState":
        path = role.storage_state_path or ""
        if not path or not os.path.exists(path):
            return None, None, {"ok": False, "error": f"storage_state_path not found: {path or '(unset)'}"}
        ctx_kwargs["storage_state"] = path
    context = browser.new_context(**ctx_kwargs)
    page = context.new_page()
    info: Dict[str, Any] = {"ok": True}
    try:
        if role.strategy == "credentials":
            from tools.auth.live_login import perform_login
            perform_login(page, {k: v for k, v in role.model_dump().items() if v is not None})
        elif role.strategy == "setup":
            from tools.playwright_scanner import execute_setup_steps
            execute_setup_steps(page, role.steps, _log)
            if not role.steps:
                info = {"ok": False, "error": "strategy setup has no steps"}
    except Exception as exc:
        info = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    return context, page, info


def relogin(page, role: RoleConfig) -> bool:
    """Re-authenticate once after a session loss (same context)."""
    try:
        if role.strategy == "credentials":
            from tools.auth.live_login import perform_login
            perform_login(page, {k: v for k, v in role.model_dump().items() if v is not None})
            return True
        if role.strategy == "setup" and role.steps:
            from tools.playwright_scanner import execute_setup_steps
            execute_setup_steps(page, role.steps, _log)
            return True
    except Exception:
        return False
    return False


def redirected_to_login(requested: str, final: str) -> bool:
    """The app bounced a non-login URL to a login page."""
    rp = urllib.parse.urlsplit(requested or "").path
    fu = urllib.parse.urlsplit(final or "")
    return bool(LOGIN_PATH.search(fu.path + ("?" + fu.query if fu.query else ""))) and not LOGIN_PATH.search(rp)


def classify_visit(requested: str, final: str, status: Optional[int], error_text: bool = False) -> str:
    """reachable | blocked | not_found | error — pure, used by the crawl and the permission matrix."""
    if status in (401, 403) or redirected_to_login(requested, final):
        return "blocked"
    if status == 404:
        return "not_found"
    if status is not None and status >= 500:
        return "error"
    if status is not None and status >= 400:
        return "blocked" if error_text else "error"
    return "reachable"


def role_names(roles: List[RoleConfig]) -> List[str]:
    return [r.name for r in roles]
