"""
permission.py — diff per-role crawl results into permission_matrix.json (task 2.6). Pure.

Input per role (built by crawl.py):
    {"role": "user",
     "pages": {url_template: {"sample_url", "access": reachable|blocked|not_found|error,
                              "via": "crawl"|"deep_link", "status", "final_url",
                              "actions": [(role, name), ...]}}}

State access per role:
    reachable           crawled (a link or a seed led there)
    reachable_unlinked  not linked for this role, but a direct URL loads it — an authorization
                        finding P3/P7 turn into tests
    blocked / not_found / error   from the visit classification
    unknown             never attempted (budget, or a URL the safety rules refuse to open)

Action visibility per role on each page template: visible (present), hidden (page reachable,
action absent), or the page's own access value when the page itself was not reachable.
`differs` marks actions that are visible for some roles and hidden for others among the roles
that reach the page (page-level blocking is reported once, in `states`).
"""

from typing import Any, Dict, List, Tuple

ActionKey = Tuple[str, str]


def _state_access(page: Dict[str, Any]) -> str:
    access = page.get("access") or "unknown"
    if access == "reachable" and page.get("via") == "deep_link":
        return "reachable_unlinked"
    return access


def build_matrix(role_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    roles = [r["role"] for r in role_results]
    templates = sorted({t for r in role_results for t in (r.get("pages") or {})})
    states: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    for tmpl in templates:
        access: Dict[str, str] = {}
        evidence: Dict[str, Dict[str, Any]] = {}
        sample = ""
        for r in role_results:
            page = (r.get("pages") or {}).get(tmpl)
            if not page:
                access[r["role"]] = "unknown"
                continue
            sample = sample or page.get("sample_url") or ""
            access[r["role"]] = _state_access(page)
            ev = {k: page.get(k) for k in ("status", "final_url", "via") if page.get(k) is not None}
            evidence[r["role"]] = ev
        states.append({"url_template": tmpl, "sample_url": sample, "access": access, "evidence": evidence})

        keys: List[ActionKey] = sorted({tuple(a) for r in role_results
                                        for a in ((r.get("pages") or {}).get(tmpl) or {}).get("actions") or []})
        for key in keys:
            vis: Dict[str, str] = {}
            for r in role_results:
                page = (r.get("pages") or {}).get(tmpl)
                state = access[r["role"]]
                if not page or state == "unknown":
                    vis[r["role"]] = "unknown"
                elif state in ("reachable", "reachable_unlinked"):
                    present = {tuple(a) for a in page.get("actions") or []}
                    vis[r["role"]] = "visible" if key in present else "hidden"
                else:
                    vis[r["role"]] = state
            # `differs`: the action is visible for some roles that reach the page and hidden for others —
            # page-level blocking is already reported in `states`, so it does not count here.
            reached = [v for v in vis.values() if v in ("visible", "hidden")]
            actions.append({"url_template": tmpl, "element": {"role": key[0], "name": key[1]},
                            "visibility": vis, "differs": len(set(reached)) > 1})
    return {"roles": roles, "states": states, "actions": actions}


def action_keys(elements: List[Dict[str, Any]]) -> List[ActionKey]:
    """Visible, named interactive elements of a state -> (role, name) action keys."""
    keys = set()
    for el in elements:
        if not (el.get("quality") or {}).get("visible"):
            continue
        role = el.get("aria_role") or (el.get("semantic_locators") or {}).get("role") or el.get("tag_name") or ""
        name = " ".join((el.get("display_text") or "").split())
        if role and name:
            keys.add((role, name[:120]))
    return sorted(keys)
