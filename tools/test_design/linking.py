"""
linking.py — deterministic case → AC linking for cases a generator could not attribute (Phase 3.3, step 1).

Content-word overlap between the case text (title, steps, oracle texts, target URL) and each candidate AC
statement. Candidates are narrowed first: the field's ACs, then the form's, then the case module's testable ACs.
Whatever stays unlinked goes to the LLM (llm.py), whose links are validated against the same candidate rules.
"""

import re
from typing import Any, Dict, Iterable, List, Set

from tools.test_design.inputs import DesignInputs

LINK_THRESHOLD = 0.3
LINK_MARGIN = 0.05
MAX_LINKS = 2
_STOP = set("""a an and are as at be by can for from has have if in into is it its of on or that the then their
there these this to was were when which while will with without any all every each other only must should not
never does do page user users shown shows show given after before same also than more most""".split())


def tokens(text: str) -> Set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9/]+", (text or "").lower()):
        if len(w) < 3 or w in _STOP:
            continue
        if w.endswith("s") and len(w) > 4 and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


# Words the BRD uses for what an oracle checks (role-matrix titles say "blocked"; criteria say "403 Access denied").
_ORACLE_WORDS = {
    "access_blocked": "access denied 403 forbidden redirects login signed",
    "page_reachable": "available access",
    "element_hidden": "hidden visible only",
    "element_visible": "visible available",
}
_ROLE_WORDS = {"guest": "without signing in signed out", "admin": "administrator administrators admin"}


def case_text(case: Dict[str, Any]) -> str:
    parts = [case.get("title", "")] + list(case.get("steps_outline") or [])
    for o in case.get("oracles") or []:
        for k in ("contains", "statement", "expected", "detail", "template"):
            if isinstance(o.get(k), str):
                parts.append(o[k])
        parts.append(_ORACLE_WORDS.get(o.get("type"), ""))
    for r in case.get("roles") or []:
        parts.append(_ROLE_WORDS.get(r, "signed"))
    t = case.get("target") or {}
    parts += [t.get("url_template") or "", t.get("to_url_template") or ""]
    return " ".join(parts)


_ACCESS = re.compile(r"\b(sign\w*|log\w* in|access\w*|admin\w*|role\w*|403|401|redirect\w*|only)\b", re.I)


def candidates_for(case: Dict[str, Any], inp: DesignInputs) -> List[Dict[str, Any]]:
    t = case.get("target") or {}
    if case.get("technique") == "role_matrix":
        # authorization rules are often stated once for the whole app (e.g. in the login module)
        return [a for a in inp.testable_acs() if "auth" in a["risk_tags"] or _ACCESS.search(a["statement"])]
    ids: List[str] = []
    if t.get("form_id"):
        form = next((f for f in inp.forms if f.form_id == t["form_id"]), None)
        if form is not None:
            fld = next((f for f in form.fields if f.name == t.get("field")), None)
            ids = list(fld.ac_ids) if fld is not None and fld.ac_ids else list(form.ac_ids)
    acs = [inp.ac(a) for a in ids if inp.ac(a)]
    if not acs and case.get("module_id"):
        acs = [a for a in inp.testable_acs() if a["module_id"] == case["module_id"]]
    return acs or inp.testable_acs()


def score(case_tokens: Set[str], ac: Dict[str, Any]) -> float:
    at = tokens(ac["statement"])
    if not at:
        return 0.0
    return len(case_tokens & at) / min(len(at), 12)


def link(case: Dict[str, Any], inp: DesignInputs) -> List[str]:
    ct = tokens(case_text(case))
    scored = sorted(((score(ct, a), a["id"]) for a in candidates_for(case, inp)), key=lambda x: (-x[0], x[1]))
    # navigation cases share page words with almost every criterion of their module: demand a stronger match
    threshold = 0.5 if case["technique"] == "state_transition" else LINK_THRESHOLD
    if not scored or scored[0][0] < threshold:
        return []
    best = scored[0][0]
    return sorted(i for s, i in scored if s >= best - LINK_MARGIN)[:MAX_LINKS]


def link_unattributed(cases: Iterable[Dict[str, Any]], inp: DesignInputs) -> List[str]:
    """Link every case without ac_ids in place; returns the ids still unlinked."""
    left = []
    for c in cases:
        if c.get("ac_ids"):
            continue
        if c["technique"] == "role_matrix":     # attributed by rule in role_matrix.py; word overlap misleads here
            left.append(c["id"])
            continue
        ids = link(c, inp)
        if ids:
            c["ac_ids"] = ids
            c["ac_link"] = "token"
        else:
            left.append(c["id"])
    return left


def apply_llm_links(cases: Iterable[Dict[str, Any]], links: Dict[str, List[str]], inp: DesignInputs) -> int:
    """LLM links are applied only to still-unlinked cases and only with ids among that case's candidates."""
    n = 0
    for c in cases:
        if c.get("ac_ids") or c["id"] not in links:
            continue
        allowed = {a["id"] for a in candidates_for(c, inp)}
        ids = sorted(a for a in links[c["id"]] if a in allowed)
        if ids:
            c["ac_ids"] = ids[:MAX_LINKS]
            c["ac_link"] = "llm"
            n += 1
    return n


def unlinked(cases: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in cases if not c.get("ac_ids")]
