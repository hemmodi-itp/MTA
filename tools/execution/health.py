"""
health.py — Phase 10.4: pre-run environment health check. A failing check makes the run `environment_blocked`
instead of producing hundreds of failed tests that say nothing about the product.

project.yaml (optional; the base-URL check runs whenever the block exists):
    health_check:
      enabled: true
      timeout_s: 10
      auth_url: /products          # a page that needs a session: a valid role session must NOT be sent to the login
      seed:                        # data the suite needs; each request is made as `role` (default: no session)
        - {path: /api/products, role: user, status: 200, contains: "Pragmatic"}

Checks
    base_url   the app answers (any status < 500)
    auth       every role storage state (execution.role_auth) still opens `auth_url` without a redirect to the login;
               an expired one is refreshed once (tools/auth/role_states.py, force) and checked again
    seed       each seed request answers with its status and contains its text
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

import yaml


def config(project_dir: str) -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(project_dir, "project.yaml"), encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return None
    hc = raw.get("health_check")
    if not isinstance(hc, dict) or hc.get("enabled") is False:
        return None
    return {**hc, "_raw": raw}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(url: str, cookies: Optional[List[dict]] = None, timeout: float = 10.0):
    """(status, location, body) without following redirects; status 0 = unreachable."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(url)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{c['name']}={c['value']}" for c in cookies))
    try:
        with opener.open(req, timeout=timeout) as resp:      # noqa: S310 — the project's own app
            return resp.status, resp.headers.get("Location", ""), resp.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", "") if exc.headers else "", ""
    except Exception as exc:
        return 0, "", f"{type(exc).__name__}: {str(exc)[:200]}"


def _role_cookies(project_dir: str, role: str) -> Optional[List[dict]]:
    from tools.auth.role_states import role_file_name
    path = os.path.join(project_dir, ".auth", role_file_name(role))
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("cookies") or []
    except (OSError, ValueError):
        return None


def check(project_dir: str, base_url: str, refresh: Optional[Callable[[str], Any]] = None,
          fetch: Callable = _get, base_only: bool = False) -> Dict[str, Any]:
    """{ok, checks: [{name, ok, detail}]}. `refresh(role)` re-creates one role's storage state.
    `base_only`: just the base-URL check — run before the role logins, so a dead app is blocked in seconds."""
    cfg = config(project_dir)
    if cfg is None:
        return {"ok": True, "checks": [], "skipped": "no health_check block in project.yaml"}
    timeout = float(cfg.get("timeout_s") or 10)
    checks: List[Dict[str, Any]] = []
    status, _loc, body = fetch(base_url, None, timeout)
    checks.append({"name": "base_url", "ok": 0 < status < 500,
                   "detail": f"{base_url} -> {status or body}"})
    if not checks[-1]["ok"] or base_only:
        return {"ok": checks[-1]["ok"], "checks": checks}

    raw = cfg["_raw"]
    roles = ((raw.get("auth") or {}).get("roles") or {})
    role_auth = bool((raw.get("execution") or {}).get("role_auth"))
    auth_url = urljoin(base_url.rstrip("/") + "/", str(cfg.get("auth_url") or "").lstrip("/")) if cfg.get("auth_url") else None
    if role_auth and auth_url:
        for role, spec in roles.items():
            if (spec or {}).get("anonymous"):
                continue
            ok, detail = _session_ok(project_dir, role, auth_url, fetch, timeout)
            if not ok and refresh is not None:
                refresh(role)
                ok, detail2 = _session_ok(project_dir, role, auth_url, fetch, timeout)
                detail = f"{detail}; refreshed -> {detail2}"
            checks.append({"name": f"auth:{role}", "ok": ok, "detail": detail})

    for item in cfg.get("seed") or []:
        url = urljoin(base_url.rstrip("/") + "/", str(item.get("path", "")).lstrip("/"))
        cookies = _role_cookies(project_dir, item["role"]) if item.get("role") else None
        st, _l, text = fetch(url, cookies, timeout)
        ok = st == int(item.get("status", 200)) and (not item.get("contains") or item["contains"] in text)
        checks.append({"name": f"seed:{item.get('path')}", "ok": ok,
                       "detail": f"{url} -> {st}" + ("" if ok or not item.get("contains") else f", missing '{item['contains']}'")})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def _session_ok(project_dir: str, role: str, url: str, fetch: Callable, timeout: float):
    cookies = _role_cookies(project_dir, role)
    if cookies is None:
        return False, f"no storage state for role '{role}'"
    st, loc, _ = fetch(url, cookies, timeout)
    expired = st in (401, 403) or (300 <= st < 400 and "login" in (loc or "").lower())
    return (not expired and 0 < st < 500), f"{url} as {role} -> {st}{(' ' + loc) if loc else ''}"
