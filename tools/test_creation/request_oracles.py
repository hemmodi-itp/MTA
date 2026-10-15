"""
request_oracles.py — ground every generated request oracle (verifyRequest / verifyNoRequest) in what discovery saw.

An LLM plan can name an endpoint the app does not have — e.g. copy a prompt example ("POST /api/login") for an app
whose login form posts to /login — or demand "2xx" from a submit the app answers with a redirect. Such a step can never
pass on a correct app: a false failure. Before rendering, each request step is checked against the observed
endpoints (form_model form actions, api_inventory traffic, white-box code_rules routes):

    known endpoint                 kept; a positive status ("2xx" / "3xx") the endpoint was never seen answering with
                                   becomes "success" (2xx or 3xx) — a 4xx / 5xx still fails
    unknown endpoint, the test     rewritten to that form's method + action (the request the test really makes)
      submits one known form on
      the page it opens
    unknown endpoint otherwise     the step is dropped (a verifyNoRequest on a path nobody calls proves nothing)
    bodyContains                   kept only when the test itself typed that value

Every change is returned so the caller can log it; nothing is silent. Pure, no I/O.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

REQUEST_ACTIONS = ("verifyRequest", "verifyNoRequest")
_POSITIVE = re.compile(r"^\s*[23]xx\s*$|^\s*success\s*$", re.I)


def _template(path: str) -> str:
    path = (path or "").split("?")[0].split("#")[0]
    path = re.sub(r"^[a-z]+://[^/]+", "", path, flags=re.I)
    return re.sub(r"/\d+(?=/|$)", "/{id}", path.rstrip("/") or "/")


def known_endpoints(form_model: Optional[dict], api_inventory: Optional[dict],
                    code_rules: Optional[dict] = None) -> List[Dict[str, Any]]:
    """[{method, template, statuses: {code: n}, page}] — `page` is the url_template of the form's own page."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def add(method: str, path: str, statuses: Optional[dict] = None, page: Optional[str] = None):
        key = ((method or "GET").upper(), _template(path))
        e = out.setdefault(key, {"method": key[0], "template": key[1], "statuses": {}, "pages": []})
        for code, n in (statuses or {}).items():
            e["statuses"][str(code)] = e["statuses"].get(str(code), 0) + int(n or 0)
        if page and page not in e["pages"]:
            e["pages"].append(page)

    for f in (form_model or {}).get("forms") or []:
        if f.get("action") or f.get("url"):
            add(f.get("method") or "get", f.get("action") or f.get("url"), None, f.get("url_template"))
    for e in (api_inventory or {}).get("endpoints") or []:
        add(e.get("method"), e.get("path_template") or e.get("path") or "", e.get("statuses"))
    for r in (code_rules or {}).get("routes") or []:
        add(r.get("method"), r.get("path_template") or "")
    return list(out.values())


def _runtime_regex(pattern: str) -> re.Pattern:
    """ActionEngine's patternToRegExp: regex specials escaped, `*` -> `.*`, searched anywhere in the URL."""
    return re.compile("".join(".*" if ch == "*" else re.escape(ch) for ch in (pattern or "")))


def match(method: str, pattern: str, endpoints: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The observed endpoint a request step refers to: same method, and the runtime pattern matches its path
    (an exact template match first)."""
    rx = _runtime_regex(pattern)
    cands = [e for e in endpoints if e["method"] == (method or "").upper()]
    cands.sort(key=lambda e: e["template"] != _template(pattern.replace("*", "1")))
    return next((e for e in cands if rx.search(e["template"].replace("{id}", "1"))), None)


def _pages(test: dict) -> List[str]:
    return [_template(s.get("value") or "") for s in test.get("steps") or []
            if isinstance(s, dict) and s.get("action") == "navigate" and s.get("value")]


def _typed(test: dict) -> List[str]:
    return [str(s.get("value")) for s in test.get("steps") or []
            if isinstance(s, dict) and s.get("action") in ("enterText", "clearAndEnterText") and s.get("value")]


def _submitted_form(test: dict, endpoints: List[Dict[str, Any]], default_page: Optional[str]) -> Optional[dict]:
    """The one non-GET form endpoint living on the page(s) this test opens (None when zero or ambiguous)."""
    pages = _pages(test) or ([default_page] if default_page else [])
    forms = [e for e in endpoints if e["method"] != "GET" and set(e["pages"]) & set(pages)]
    return forms[0] if len(forms) == 1 else None


def ground_plan(plan: dict, endpoints: List[Dict[str, Any]], default_page: Optional[str] = None
                ) -> Tuple[dict, List[Dict[str, Any]]]:
    """(plan with every request step grounded, changes). Without any known endpoint the plan is returned as is."""
    if not endpoints:
        return plan, []
    plan = copy.deepcopy(plan)
    changes: List[Dict[str, Any]] = []
    for test in plan.get("tests") or []:
        if not isinstance(test, dict):
            continue
        kept = []
        for step in test.get("steps") or []:
            if not (isinstance(step, dict) and step.get("action") in REQUEST_ACTIONS):
                kept.append(step)
                continue
            before = {k: step.get(k) for k in ("method", "urlPattern", "status", "bodyContains") if step.get(k) is not None}
            ep = match(step.get("method") or "GET", step.get("urlPattern") or "", endpoints)
            if ep is None:
                form = _submitted_form(test, endpoints, default_page)
                if form is None:
                    changes.append({"test": test.get("name"), "change": "dropped", "before": before,
                                    "reason": "no observed endpoint matches, and the test submits no single known form"})
                    continue
                step = dict(step, method=form["method"], urlPattern=form["template"].replace("{id}", "*"))
                ep = form
                changes.append({"test": test.get("name"), "change": "rewritten", "before": before,
                                "after": {"method": step["method"], "urlPattern": step["urlPattern"]},
                                "reason": "unknown endpoint; the form this test submits posts here"})
            status = step.get("status")
            if step["action"] == "verifyRequest" and isinstance(status, str) and _POSITIVE.match(status) \
                    and status.strip().lower() != "success":
                seen = {c[0] for c in ep["statuses"]}
                if seen and status.strip()[0] not in seen:
                    changes.append({"test": test.get("name"), "change": "status", "before": before,
                                    "after": {"status": "success"},
                                    "reason": f"{ep['method']} {ep['template']} was seen answering {sorted(ep['statuses'])}"})
                    step = dict(step, status="success")
            body = step.get("bodyContains")
            if body is not None and str(body) not in " ".join(_typed(test)):
                changes.append({"test": test.get("name"), "change": "bodyContains dropped", "before": before,
                                "reason": f"the test never types {str(body)[:40]!r}"})
                step = {k: v for k, v in step.items() if k != "bodyContains"}
            kept.append(step)
        test["steps"] = kept
    return plan, changes
