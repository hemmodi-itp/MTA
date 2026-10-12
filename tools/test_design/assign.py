"""
assign.py — put every case in a scenario (= a spec file ScriptGeneration writes), or report why it can't be.

Rules (design note D5):
  * a role_matrix case needs a module whose setup signs in as that role (guest → a module without sign-in, else
    any module with "log out first"); other cases need a module whose role can reach the case's page;
  * within the module: the scenario sharing the most ACs with the case, else the module's first scenario;
  * no module / no scenario → cut with reason `no_scenario`.
"""

from typing import Any, Dict, List, Optional

from tools.test_design.inputs import DesignInputs, norm_template


def _reachable(inp: DesignInputs, template: Optional[str], role: Optional[str]) -> bool:
    if not template or role is None:
        return True
    st = inp.states.get(norm_template(template))
    if st is None:
        return True
    if role in st.access:
        return st.access[role] == "reachable"
    return role in st.roles or not st.roles


def _scenarios(inp: DesignInputs, module_id: str) -> List[Dict[str, Any]]:
    return [s for s in inp.scenarios if s.get("module_id") == module_id]


def _pick_scenario(inp: DesignInputs, module_id: str, ac_ids: List[str]) -> Optional[str]:
    scen = _scenarios(inp, module_id)
    if not scen:
        return None
    acs = set(ac_ids)
    best = sorted(scen, key=lambda s: (-len(acs & set(s.get("ac_ids") or [])), str(s.get("scenario_id"))))[0]
    return best.get("scenario_id")


def assign(cases: List[Dict[str, Any]], inp: DesignInputs) -> List[Dict[str, Any]]:
    """Set scenario_id / module_id in place. Returns the cases that could not be assigned."""
    failed = []
    module_ids = [m["id"] for m in inp.modules] or sorted({s.get("module_id") for s in inp.scenarios if s.get("module_id")})
    for c in cases:
        t = c.get("target") or {}
        template = t.get("url_template")
        home = c.get("module_id")
        if c["technique"] == "role_matrix":
            role = (c.get("roles") or [None])[0]
            options = [m for m in module_ids if inp.module_role(m) == role]
            if not options and role == "guest":
                options = [home] if home else module_ids[:1]
                if "log out first" not in c["preconditions"]:
                    c["preconditions"].insert(0, "log out first")
            if not options and role in inp.role_logins:
                options = [home] if home else module_ids[:1]
                c["tags"] = sorted(set(c["tags"]) | {"needs_role_switch"})
            ordered = sorted(options, key=lambda m: (m != home, m))
        else:
            ordered = [home] if home else []
            ordered += [m for m in module_ids if m not in ordered]
            ordered = [m for m in ordered if _reachable(inp, template, inp.module_role(m))]
            # stay in the home module when its scenarios share the case's ACs, else the first reachable one
            if home in ordered:
                ordered.remove(home)
                ordered.insert(0, home)
        chosen = None
        for m in ordered:
            sid = _pick_scenario(inp, m, c.get("ac_ids") or [])
            if sid:
                chosen = (m, sid)
                break
        if chosen is None:
            failed.append(c)
            continue
        c["module_id"], c["scenario_id"] = chosen
    return failed
