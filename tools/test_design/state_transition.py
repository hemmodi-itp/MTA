"""
state_transition.py — state-transition testing from app_map.json (Phase 3.2).

    valid (0-switch)   every distinct page→page transition; a navigation link present on most pages ("global nav")
                       is tested once, from one representative page                                   [standard]
    invalid            deep link to a flow step without its prerequisite step; back button after a POST
                       submit; refresh right after a POST submit (no duplicate re-submission)        [thorough]
    1-switch           pairs of consecutive transitions through pages tied to P0/P1 criteria          [exhaustive]
"""

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from tools.test_design.cases import new_case
from tools.test_design.inputs import DesignInputs, Transition

GLOBAL_SHARE = 0.6


def global_links(transitions: List[Transition]) -> Set[Tuple[str, str]]:
    """(to_template, via) pairs present on at least GLOBAL_SHARE of the pages that have outgoing links."""
    sources: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    pages = {t.from_t for t in transitions}
    for t in transitions:
        sources[(t.to_t, t.via)].add(t.from_t)
    if len(pages) < 3:
        return set()
    return {k for k, v in sources.items() if len(v) / len(pages) >= GLOBAL_SHARE}


def _role(inp: DesignInputs, roles: List[str], template: str) -> str:
    st = inp.states.get(template)
    pref = inp.module_role(st.module_id) if st else None
    if pref in roles:
        return pref
    return sorted(roles)[0] if roles else ""


def generate(inp: DesignInputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    trans = inp.transitions
    if not trans:
        return out
    glob = global_links(trans)
    done_global: Set[Tuple[str, str]] = set()
    local: List[Transition] = []
    templated_done: Set[Tuple[str, str]] = set()
    for t in trans:                                    # sorted by (from, to, via) in inputs
        if "{" in t.to_t:                              # one case per templated target (8 product links → 1)
            if (t.from_t, t.to_t) in templated_done:
                continue
            templated_done.add((t.from_t, t.to_t))
        if (t.to_t, t.via) in glob:
            if (t.to_t, t.via) in done_global:
                continue
            done_global.add((t.to_t, t.via))
        else:
            local.append(t)
        role = _role(inp, t.roles, t.from_t)
        src = inp.states.get(t.from_t)
        dst = inp.states.get(t.to_t)
        out.append(new_case(
            key=f"st|0|{t.from_t}|{t.to_t}|{t.via}",
            title=f"{t.from_t} → {t.to_t} via '{t.via[:40]}'" + (" (global navigation)" if (t.to_t, t.via) in glob else ""),
            technique="state_transition", test_type="positive", level="standard",
            target={"kind": "transition", "url_template": t.from_t, "sample_url": src.sample_url if src else None,
                    "to_url_template": t.to_t},
            roles=[role] if role else [], preconditions=[f"signed in as {role}" if role and role != "guest" else
                                                         "signed out", f"on {t.from_t}"],
            steps_outline=[f"click '{t.via}'"],
            oracles=[{"type": "url_matches", "template": t.to_t, "source": "app_map"},
                     {"type": "status_ok", "source": "app_map"}],
            source="app_map", module_id=(src.module_id if src else None), tags=["0-switch"],
            likelihood=0.3 + (0.1 if dst and dst.module_id else 0.0),
        ))

    # invalid: deep link to a flow step whose only entry is one other page (not global nav)
    preds: Dict[str, Set[str]] = defaultdict(set)
    for t in local:
        preds[t.to_t].add(t.from_t)
    for target, sources in sorted(preds.items()):
        if len(sources) != 1 or target in {g[0] for g in glob}:
            continue
        prev = next(iter(sources))
        st = inp.states.get(target)
        role = _role(inp, st.roles if st else [], target)
        out.append(new_case(
            key=f"st|invalid|deeplink|{target}|{prev}",
            title=f"Open {target} directly without going through {prev} first",
            technique="state_transition", test_type="negative", level="thorough",
            target={"kind": "state", "url_template": target, "sample_url": st.sample_url if st else None},
            roles=[role] if role else [], preconditions=[f"signed in as {role}" if role and role != "guest" else
                                                         "signed out", f"{prev} step not completed"],
            steps_outline=[f"navigate directly to {st.sample_url if st and st.sample_url else target}"],
            oracles=[{"type": "guarded", "detail": f"the app refuses or redirects; it must not act as if {prev} was done",
                      "source": "app_map"}, {"type": "no_server_error", "source": "catalog"}],
            source="app_map", module_id=st.module_id if st else None, tags=["invalid-transition", "deep-link"],
            likelihood=0.7,
        ))
    for form in inp.forms:
        if form.method != "post" or form.twin_of or (form.submit or {}).get("destructive"):
            continue
        for kind, step in (("back", "press the browser Back button, then submit again if the form is shown"),
                           ("refresh", "reload the page right after submitting")):
            out.append(new_case(
                key=f"st|invalid|{kind}|{form.form_id}",
                title=f"{kind.capitalize()} after submitting {form.dom_id or 'form'} on {form.url_template} does not re-submit",
                technique="state_transition", test_type="negative", level="thorough",
                target={"kind": "form", "form_id": form.form_id, "url_template": form.url_template,
                        "sample_url": form.sample_url},
                roles=[form.role] if form.role else [], preconditions=[f"on {form.url_template}"],
                steps_outline=["fill the form with valid values", "submit", step],
                oracles=[{"type": "single_record_created", "source": "catalog"},
                         {"type": "no_server_error", "source": "catalog"}],
                source="app_map+catalog", module_id=form.module_id, tags=["invalid-transition", kind],
                likelihood=0.6,
            ))

    # 1-switch over P0/P1 pages
    hot = {t for t, st in inp.states.items() if _hot(inp, t)}
    by_from: Dict[str, List[Transition]] = defaultdict(list)
    for t in local:
        by_from[t.from_t].append(t)
    for a in local:
        if a.from_t not in hot and a.to_t not in hot:
            continue
        for b in by_from.get(a.to_t, []):
            if b.to_t == a.from_t:
                continue
            role = _role(inp, sorted(set(a.roles) & set(b.roles)) or a.roles, a.from_t)
            out.append(new_case(
                key=f"st|1|{a.from_t}|{a.to_t}|{b.to_t}|{a.via}|{b.via}",
                title=f"{a.from_t} → {a.to_t} → {b.to_t}", technique="state_transition", test_type="positive",
                level="exhaustive", target={"kind": "transition", "url_template": a.from_t, "to_url_template": b.to_t},
                roles=[role] if role else [], preconditions=[f"on {a.from_t}"],
                steps_outline=[f"click '{a.via}'", f"click '{b.via}'"],
                oracles=[{"type": "url_matches", "template": b.to_t, "source": "app_map"}],
                source="app_map", module_id=inp.states[a.from_t].module_id if a.from_t in inp.states else None,
                tags=["1-switch"], likelihood=0.35,
            ))
    return out


def _hot(inp: DesignInputs, template: str) -> bool:
    for form in inp.forms:
        if form.url_template == template and any(inp.ac(a) and inp.ac(a)["priority"] in ("P0", "P1") for a in form.ac_ids):
            return True
    st = inp.states.get(template)
    return bool(st and st.module_id and any(a["module_id"] == st.module_id and a["priority"] in ("P0", "P1")
                                            for a in inp.acs))
