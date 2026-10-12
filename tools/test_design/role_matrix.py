"""
role_matrix.py — authorization tests from permission_matrix.json (Phase 3.2).

Every page cell (url_template × role) becomes a test: allowed → the page works; denied → the page is blocked when
opened by direct URL (UI). The API half of "blocked by URL **and** API" needs the API inventory work of P8.

    page cells where access differs between roles (authorization boundaries)   [standard]
    page cells where every role has the same access                            [thorough]
    action cells (an element visible to some roles, hidden from others)        [standard / exhaustive]

The EXPECTED access of a page cell comes from the BRD when a criterion states it (plan 5.2: BRD > observed); the
crawl's observation is only the fallback. When the two disagree (e.g. the crawl ran against a build where a regular
user can open /admin), the case keeps the BRD oracle and the disagreement is returned as a conflict for human
review — an observed defect is never turned into the expected behaviour.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from tools.test_design.cases import new_case
from tools.test_design.inputs import DesignInputs, norm_template
from tools.test_design.use_case import is_negative

_TO_LOGIN = re.compile(r"\bredirects? to the login\b", re.I)
_ANON = re.compile(r"\bwithout signing in\b", re.I)
_LOGOUT = re.compile(r"\blogs? out\b|\blogout\b", re.I)          # session-invalidation rules, not page access
_ADMIN = re.compile(r"\badmin(?:istrator)?s?\b", re.I)
_OTHERS = re.compile(r"\b(any other|other signed-in|non-admin\w*|customers?|regular users?)\b", re.I)
_ONLY = re.compile(r"\bonly\b", re.I)


def _page_rx(template: str) -> Tuple["re.Pattern[str]", Optional["re.Pattern[str]"]]:
    seg = template.strip("/").split("/")[0] if template.strip("/") else ""
    literal = re.compile(rf"(?<![\w/]){re.escape(template)}`?(?![\w/{{])", re.I)   # not inside /api/products
    named = re.compile(rf"\b{re.escape(seg)} page\b", re.I) if seg else None
    return literal, named


def brd_access(inp: DesignInputs, template: str, role: str) -> Tuple[Optional[bool], List[str]]:
    """(expected access stated by the BRD or None, the ACs that state it). Rules (word overlap misleads here):
      guest     blocked ← "redirects to the login" (not a logout rule); allowed ← names the page + "without signing in"
      admin     allowed ← names the page literally, positive, mentions administrators
      others    blocked ← names the page literally, negative, mentions "any other / customers / non-admin";
                blocked ← "only … administrators"; allowed ← names the page literally, positive, no role words"""
    literal, named = _page_rx(template)
    allowed_by: List[str] = []
    blocked_by: List[str] = []
    for a in inp.testable_acs():
        s = a["statement"]
        if role == "guest":
            names_page = literal.search(s) or (named is not None and named.search(s))
            if _ANON.search(s) and names_page:
                allowed_by.append(a["id"])
            elif _TO_LOGIN.search(s) and not _LOGOUT.search(s):
                blocked_by.append(a["id"])
            continue
        if not literal.search(s) or _ANON.search(s):
            continue
        admin_words, other_words, neg = bool(_ADMIN.search(s)), bool(_OTHERS.search(s)), is_negative(s)
        if role == "admin":
            if admin_words and not neg:
                allowed_by.append(a["id"])
        elif neg and (other_words or not admin_words):
            blocked_by.append(a["id"])
        elif not neg and admin_words and _ONLY.search(s):
            blocked_by.append(a["id"])
        elif not neg and not admin_words and not other_words:
            allowed_by.append(a["id"])
    if role == "guest" and allowed_by:
        return True, allowed_by                       # a page named as anonymous beats the general redirect rule
    if blocked_by and not allowed_by:
        return False, blocked_by
    if allowed_by and not blocked_by:
        return True, allowed_by
    return None, []


def acs_for_cell(inp: DesignInputs, template: str, role: str, allowed: bool) -> List[str]:
    expected, ids = brd_access(inp, template, role)
    return ids if expected is allowed else []


def page_cells(inp: DesignInputs) -> List[Dict[str, Any]]:
    """One record per (page, role): observed access, BRD-expected access and the ACs behind it."""
    out = []
    seen = set()
    for cell in sorted((inp.permission or {}).get("states") or [], key=lambda s: s.get("url_template", "")):
        t = norm_template(cell.get("url_template", ""))
        access = cell.get("access") or {}
        if t in seen or not access:
            continue
        seen.add(t)
        for role, acc in sorted(access.items()):
            expected, ac_ids = brd_access(inp, t, role)
            out.append({"template": t, "role": role, "observed": acc == "reachable", "expected": expected,
                        "ac_ids": ac_ids, "differs": len(set(access.values())) > 1, "cell": cell,
                        "evidence": (cell.get("evidence") or {}).get(role) or {}})
    return out


def conflicts(inp: DesignInputs) -> List[Dict[str, Any]]:
    """Page cells where the crawl saw the opposite of what the BRD states (potential defects; plan 5.2)."""
    return [{"ac_id": c["ac_ids"][0], "form_id": f"page:{c['template']}", "field": c["role"], "probe": "direct_url",
             "brd": (inp.ac(c["ac_ids"][0]) or {}).get("statement", "")[:300],
             "observed": f"{'reachable' if c['observed'] else 'blocked'} for {c['role']}"}
            for c in page_cells(inp) if c["expected"] is not None and c["expected"] != c["observed"]]


def generate(inp: DesignInputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    pm = inp.permission or {}
    for c in page_cells(inp):
        t, role, cell, ev = c["template"], c["role"], c["cell"], c["evidence"]
        st = inp.states.get(t)
        brd_known = c["expected"] is not None
        allowed = c["expected"] if brd_known else c["observed"]
        source = "brd" if brd_known else "observed"
        if allowed:
            oracles = [{"type": "page_reachable", "template": t, "source": source}]
        else:
            oracles = [{"type": "access_blocked", "template": t, "source": source,
                        "observed_status": ev.get("status"), "observed_final_url": ev.get("final_url")}]
        tags = ["authz", "direct-url"] + (["brd-vs-observed"] if brd_known and allowed != c["observed"] else [])
        pre = ["signed out"] if role == "guest" or not inp.role_logins.get(role) else [f"signed in as {role}"]
        out.append(new_case(
            key=f"rm|page|{t}|{role}",
            title=f"{role} opening {t} by direct URL is {'allowed' if allowed else 'blocked'}",
            technique="role_matrix", test_type="positive" if allowed else "negative",
            level="standard" if c["differs"] or (brd_known and allowed != c["observed"]) else "thorough",
            target={"kind": "state", "url_template": t, "sample_url": cell.get("sample_url") or (st.sample_url if st else None)},
            roles=[role], preconditions=pre, ac_ids=c["ac_ids"] if brd_known else [],
            steps_outline=[f"navigate directly to {cell.get('sample_url') or t}"],
            oracles=oracles, source=source, confidence=1.0 if brd_known else 0.7,
            module_id=st.module_id if st else inp.module_for_path(t),
            tags=tags, likelihood=0.9 if (c["differs"] or tags[-1] == "brd-vs-observed") and not allowed else 0.5,
        ))
    # Action cells: an element shown to some roles and not others. Only a link INTO a page whose access differs
    # by role is an authorization boundary (standard); other differences are often state, not permission
    # (e.g. an empty cart hides "Place order"), so they stay exhaustive. Each (element, role) is tested once.
    # Their oracle is observed only (no BRD rule names individual links) — confidence 0.6, never standalone proof.
    boundary_pages = {norm_template(c.get("url_template", "")) for c in pm.get("states") or []
                      if len(set((c.get("access") or {}).values())) > 1}
    link_targets: Dict[str, set] = {}
    for tr in inp.transitions:
        link_targets.setdefault(tr.via, set()).add(tr.to_t)
    done = set()
    for act in sorted(pm.get("actions") or [], key=lambda a: (a.get("url_template", ""), str(a.get("element")))):
        if not act.get("differs"):
            continue
        t = norm_template(act.get("url_template", ""))
        el = act.get("element") or {}
        name = el.get("name") or el.get("role") or "element"
        st = inp.states.get(t)
        boundary = bool(link_targets.get(name, set()) & boundary_pages)
        for role, vis in sorted((act.get("visibility") or {}).items()):
            if (name, role) in done:
                continue
            done.add((name, role))
            if vis == "blocked":
                continue                                    # the page itself is blocked: covered by the page cell
            visible = vis == "visible"
            out.append(new_case(
                key=f"rm|action|{t}|{name}|{role}",
                title=f"'{name}' on {t} is {'visible' if visible else 'hidden'} for {role}",
                technique="role_matrix", test_type="positive" if visible else "negative",
                level="standard" if boundary else "exhaustive",
                target={"kind": "state", "url_template": t, "sample_url": st.sample_url if st else None},
                roles=[role], preconditions=[f"signed in as {role}" if role != "guest" else "signed out", f"on {t}"],
                steps_outline=[f"look for {el.get('role') or 'element'} '{name}'"],
                oracles=[{"type": "element_visible" if visible else "element_hidden", "role": el.get("role"),
                          "name": name, "source": "observed"}],
                source="observed", confidence=0.6, module_id=st.module_id if st else None,
                tags=["authz", "action"], likelihood=0.7,
            ))
    return out
