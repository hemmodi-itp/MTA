"""
role_states.py — one storageState file per `auth.roles` role, before a Playwright run (Phase 4.3).

    application_assets/projects/<project>/.auth/<role>.json      (gitignored: .auth/)

Strategies (the Phase 2 `auth.roles` block, tools/discovery/deep/config.py::RoleConfig):
    anonymous     no file — the runtime `role` fixture uses an empty storage state
    storageState  the role's own storage_state_path is used as-is (checked to exist)
    credentials   live login (tools/auth/live_login.perform_login; credentials from env vars only)
    setup         module-style goto/fill/click/wait steps (tools/playwright_scanner.execute_setup_steps)

Logins reuse tools/discovery/deep/roles.open_role — the code Phase 2's role crawl already uses — in a
headless Chromium outside the Playwright test runner, so credentials never reach a trace, video,
screenshot or report. Only role names, strategies, statuses and file paths are logged; a file younger
than max_age_minutes is reused.

The TS side (application_assets/_shared/runtime/auth/roles.ts) resolves the same paths for
`test.use({ role: '<name>' })`; keep role_file_name() and roleFileName() identical.

    python -m tools.auth.role_states --project <name> [--role admin] [--force] [--headed]
"""

import argparse
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

from tools import constants
from tools.discovery.deep.config import RoleConfig, load_roles, resolve_roles

_log = logging.getLogger("workflow.auth.roles")

LOGIN_PATH = re.compile(r"/(log-?in|sign-?in)(/|$|\?|\.)", re.I)


def role_file_name(role: str) -> str:
    """Role name -> file name (same rule as roles.ts::roleFileName)."""
    return (re.sub(r"[^A-Za-z0-9_-]", "_", role).strip("_") or "role") + ".json"


def auth_dir(safe_project: str) -> str:
    return os.path.join(constants.PROJECTS_BASE, safe_project, ".auth")


def role_state_path(safe_project: str, role: RoleConfig) -> Optional[str]:
    """Where the role's storage state lives (None for anonymous)."""
    if role.strategy == "anonymous":
        return None
    if role.strategy == "storageState":
        return role.storage_state_path or None
    return os.path.join(auth_dir(safe_project), role_file_name(role.name))


def _fresh(path: str, max_age_minutes: float) -> bool:
    return os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_minutes * 60


def _still_on_login(url: str, role: RoleConfig) -> bool:
    """A setup/credentials login that did not leave the login page failed. execute_setup_steps logs
    failures without raising, so this check (or success_url) is what detects them."""
    if role.success_url:
        return not url.startswith(role.success_url) and role.success_url not in url
    return bool(LOGIN_PATH.search(url or ""))


def _capture(browser, role: RoleConfig, path: str) -> Dict[str, Any]:
    from tools.discovery.deep.roles import open_role

    context, page, info = open_role(browser, role)
    if context is None:
        return {"status": "failed", "error": info.get("error", "could not open a context")}
    try:
        if not info.get("ok"):
            return {"status": "failed", "error": info.get("error", "login failed")}
        if _still_on_login(page.url, role):
            return {"status": "failed", "error": f"still on a login page after login ({page.url.split('?')[0]})"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        context.storage_state(path=tmp)
        os.replace(tmp, path)
        return {"status": "captured"}
    except Exception as exc:  # pragma: no cover — defensive
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        try:
            context.close()
        except Exception:
            pass


def ensure_role_states(safe_project: str, roles: List[RoleConfig], *, max_age_minutes: float = 30,
                       force: bool = False, only: Optional[List[str]] = None, headless: bool = True,
                       browser_factory=None) -> Dict[str, Any]:
    """Make sure every role has a usable storage state. Never raises; a role that cannot log in is
    listed in `failed` (the run continues, and a spec using that role fails in its fixture).

    browser_factory: test seam — a context manager yielding a browser with new_context()."""
    summary: Dict[str, Any] = {"dir": auth_dir(safe_project), "roles": [], "failed": []}
    todo: List[RoleConfig] = []
    for role in roles:
        if only and role.name not in only:
            continue
        entry: Dict[str, Any] = {"name": role.name, "strategy": role.strategy}
        path = role_state_path(safe_project, role)
        if path:
            entry["path"] = path
        if role.strategy == "anonymous":
            entry["status"] = "anonymous"
        elif role.strategy == "storageState":
            entry["status"] = "ok" if path and os.path.exists(path) else "missing"
            if entry["status"] == "missing":
                entry["error"] = f"storage_state_path not found: {path or '(unset)'}"
        elif not force and _fresh(path, max_age_minutes):
            entry["status"] = "reused"
        else:
            todo.append(role)
        summary["roles"].append(entry)

    if todo:
        by_name = {e["name"]: e for e in summary["roles"]}
        try:
            factory = browser_factory or (lambda: _chromium(headless))
            with factory() as browser:
                for role in todo:
                    by_name[role.name].update(_capture(browser, role, role_state_path(safe_project, role)))
        except Exception as exc:
            for role in todo:
                by_name[role.name].setdefault("status", "failed")
                by_name[role.name].setdefault("error", f"browser launch failed: {type(exc).__name__}: {exc}"[:300])

    for e in summary["roles"]:
        if e["status"] in ("failed", "missing"):
            summary["failed"].append(e["name"])
            _log.warning("[role_auth] role '%s' (%s): %s — %s", e["name"], e["strategy"], e["status"], e.get("error", ""))
        else:
            _log.info("[role_auth] role '%s' (%s): %s%s", e["name"], e["strategy"], e["status"],
                      f" → {e['path']}" if e.get("path") else "")
    return summary


class _chromium:
    """Context manager: a headless Chromium from the Python Playwright package."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        return self._browser

    def __exit__(self, *exc):
        try:
            self._browser.close()
        finally:
            self._pw.stop()
        return False


def project_roles(raw_project_yaml: Optional[dict]) -> List[RoleConfig]:
    return load_roles(resolve_roles(raw_project_yaml or {}))


def main(argv=None) -> int:
    from tools.base_url import load_project_yaml

    ap = argparse.ArgumentParser(description="Capture .auth/<role>.json for every auth.roles role")
    ap.add_argument("--project", required=True)
    ap.add_argument("--role", action="append", help="only this role (repeatable)")
    ap.add_argument("--force", action="store_true", help="log in again even if a fresh file exists")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--max-age-minutes", type=float, default=30)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    roles = project_roles(load_project_yaml(constants.PROJECTS_BASE, args.project))
    if not roles:
        print(f"Project '{args.project}' declares no auth.roles.", file=sys.stderr)
        return 1
    summary = ensure_role_states(args.project, roles, max_age_minutes=args.max_age_minutes,
                                 force=args.force, only=args.role, headless=not args.headed)
    for e in summary["roles"]:
        print(f"  {e['name']:<16} {e['strategy']:<13} {e['status']:<10} {e.get('path') or e.get('error', '')}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
