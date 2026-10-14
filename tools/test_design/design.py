"""
design.py — the deterministic test-design pipeline (Phase 3). Pure: DesignInputs + hints in, test_cases doc out.

    generate   bva, ep, decision_table (from hints), state_transition, pairwise, use_case, crud, error_guessing,
               role_matrix
    dedupe     same id, or the same input on the same field of the same form (bva > ep > error_guessing; the
               survivor keeps every technique's ACs and an `also:<technique>` tag)
    link       generator ACs → token linking → validated LLM links
    extras     validated LLM domain cases (additive only; never replace a deterministic case)
    conflicts  BRD says reject, a probe saw the app accept → potential defect (never auto-resolved)
    risk       risk = impact × likelihood → P0–P3
    assign     case → scenario (spec file), or cut `no_scenario`
    select     profile filter, P0s, coverage floor, then risk order within the budget; rest cut `budget`

Calling design() twice with the same inputs returns byte-identical JSON (except `generated_at`, set by the caller).
"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from tools.test_design import (
    assign as assign_mod, bva, crud, decision_table, ep, error_guessing, linking, pairwise, role_matrix,
    state_transition, use_case,
)
from tools.test_design.cases import new_case, stable_json
from tools.test_design.config import level_rank
from tools.test_design.inputs import DesignInputs
from tools.test_design.models import TestCasesDoc
from tools.test_design.risk import score_all
from tools.test_design.select import select

_TECH_PRECEDENCE = {"bva": 0, "ep": 1, "error_guessing": 2}
_REJECTING_PROBES = {
    "empty": ("required", "range"), "required_missing": ("required",), "too_long": ("length",),
    "below_min": ("range",), "above_max": ("range",), "non_integer": ("range",), "wrong_type": ("range", "decimals"),
    "wrong_accept": ("accept",), "too_large": ("size",),
}


def generate_all(inp: DesignInputs, hints: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    hints = hints or {}
    neg = {h["ac_id"]: bool(h["has_negative_path"]) for h in hints.get("negative_paths") or []}
    dt_cases, tables = decision_table.generate(inp, hints.get("decision_tables") or [])
    cases = (bva.generate(inp) + ep.generate(inp) + dt_cases + state_transition.generate(inp) +
             pairwise.generate(inp) + use_case.generate(inp, neg) + crud.generate(inp) +
             error_guessing.generate(inp) + role_matrix.generate(inp))
    return cases, tables


def _signature(c: Dict[str, Any]) -> Optional[str]:
    t = c.get("target") or {}
    if t.get("kind") != "form" or not t.get("field"):
        return None
    v = (c.get("inputs") or {}).get(t["field"], {}).get("value")
    return stable_json([t.get("form_id"), t["field"], v, c["test_type"] == "negative"])


def dedupe(cases: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for c in cases:
        by_id.setdefault(c["id"], c)
    keep: Dict[str, Dict[str, Any]] = {}
    dropped: List[Dict[str, Any]] = []
    out: List[Dict[str, Any]] = []
    for c in sorted(by_id.values(), key=lambda c: (_TECH_PRECEDENCE.get(c["technique"], 9), c["id"])):
        sig = _signature(c)
        if sig is None or c["technique"] not in _TECH_PRECEDENCE:
            out.append(c)
            continue
        if sig in keep:
            k = keep[sig]
            k["ac_ids"] = sorted(set(k["ac_ids"]) | set(c["ac_ids"]))
            k["tags"] = sorted(set(k["tags"]) | {f"also:{c['technique']}"})
            k["level"] = min(k["level"], c["level"], key=level_rank)
            dropped.append(c)
            continue
        keep[sig] = c
        out.append(c)
    return out, dropped


def conflicts(inp: DesignInputs) -> List[Dict[str, Any]]:
    out = []
    for form in inp.forms:
        if form.twin_of:
            continue
        for p in form.probes:
            if not p.get("accepted"):
                continue
            fields = [f for f in form.fields if p.get("field") in (None, f.name)]
            for fld in fields:
                for kind in _REJECTING_PROBES.get(p.get("probe"), ()):
                    c = fld.constraints.get(kind) or {}
                    if not fld.kind_acs.get(kind) or (kind == "required" and not c.get("value", True)):
                        continue                  # no BRD criterion states this rule → nothing to disagree with
                    ac = (fld.kind_acs.get(kind) or [None])[0]
                    stmt = inp.ac(ac)["statement"] if ac and inp.ac(ac) else f"{kind} constraint"
                    out.append({"ac_id": ac, "form_id": form.form_id, "field": fld.name, "probe": p.get("probe"),
                                "brd": stmt[:300], "observed": f"accepted ({p.get('value_rule')})"})
                    break
    out += role_matrix.conflicts(inp)                 # permission cells: crawl vs BRD-stated access
    uniq = {stable_json(c): c for c in out}
    return [uniq[k] for k in sorted(uniq)]


def extra_cases(extras: List[Dict[str, Any]], inp: DesignInputs, module_id: str) -> List[Dict[str, Any]]:
    out = []
    for e in extras:
        acs = [a for a in e["ac_ids"] if inp.ac(a) and inp.ac(a)["testability"] == "ui"]
        if not acs:
            continue
        out.append(new_case(
            key=f"llm|{module_id}|{e['title'].strip().lower()}", title=e["title"], technique="llm_domain",
            test_type=e["test_type"], level="standard", target={"kind": "ac"}, ac_ids=acs,
            preconditions=e.get("preconditions") or [], steps_outline=e["steps_outline"],
            oracles=[{"type": "outcome", "expected": e["expected"], "source": "llm_inferred"}],
            source="llm_inferred", confidence=0.6, module_id=module_id, tags=["llm"], likelihood=0.5,
        ))
        out[-1]["ac_link"] = "llm"
    return out


def cite_code(cases: List[Dict[str, Any]], inp: DesignInputs) -> None:
    """Phase 8.2: every case whose value comes from a code rule cites that rule's file:line."""
    fields = {(f.form_id, fld.name): fld for f in inp.forms for fld in f.fields}
    for c in cases:
        if "code" not in str(c.get("source") or ""):
            continue
        t = c.get("target") or {}
        fld = fields.get((t.get("form_id"), t.get("field")))
        if fld is not None:
            kinds = [k for k in fld.citations if k in (c.get("tags") or [])]       # the rule this case exercises
            c["citations"] = sorted({fld.citations[k] for k in kinds} or {v for v in fld.citations.values() if v})


def design(inp: DesignInputs, profile: str, budget: Dict[str, Any], hints: Optional[Dict[str, Any]] = None,
           llm_status: Optional[Dict[str, Any]] = None, extras: Optional[List[Dict[str, Any]]] = None,
           rejected_extras: int = 0) -> Dict[str, Any]:
    hints = hints or {}
    cases, tables = generate_all(inp, hints)
    cases, _dupes = dedupe(cases)
    linking.link_unattributed(cases, inp)
    linking.apply_llm_links(cases, {h["case_id"]: h["ac_ids"] for h in hints.get("ac_links") or []}, inp)
    known = {c["id"] for c in cases}
    for e in extras or []:
        if e["id"] not in known:
            cases.append(e)
            known.add(e["id"])
    cite_code(cases, inp)
    score_all(cases, inp)
    unassigned = assign_mod.assign(cases, inp)
    unassigned_ids = {c["id"] for c in unassigned}
    pool = [c for c in cases if c["id"] not in unassigned_ids]
    testable = [a["id"] for a in inp.testable_acs()]
    smoke_acs = [a["id"] for a in inp.testable_acs() if a["priority"] == "P0"]
    selected, cut, report = select(pool, profile, budget, testable, smoke_acs)
    cut += [dict(c, _cut_reason="no_scenario", _cut_detail="no module/scenario can host this case")
            for c in unassigned if level_rank(c["level"]) <= level_rank(profile)]
    excluded = sum(1 for c in cases if level_rank(c["level"]) > level_rank(profile))

    selected.sort(key=lambda c: (int(c["priority"][1]), -c["risk_score"], c["id"]))
    final_cases = [{k: v for k, v in c.items() if not k.startswith("_")} for c in selected]
    cut_out = [{"id": c["id"], "title": c["title"], "technique": c["technique"], "priority": c["priority"],
                "risk_score": c["risk_score"], "ac_ids": c["ac_ids"], "reason": c["_cut_reason"],
                "detail": c.get("_cut_detail")}
               for c in sorted(cut, key=lambda c: (int(c["priority"][1]), -c["risk_score"], c["id"]))]

    covered = sorted({a for c in final_cases for a in c["ac_ids"]} & set(testable))
    summary = {
        "generated": len(cases), "selected": len(final_cases), "cut": len(cut_out),
        "by_technique": _count(final_cases, "technique"), "by_priority": _count(final_cases, "priority"),
        "by_type": _count(final_cases, "test_type"), "acs_testable": len(testable), "acs_with_case": len(covered),
        "ac_coverage_pct": round(100.0 * len(covered) / len(testable), 1) if testable else 0.0,
        "acs_without_case": sorted(set(testable) - set(covered)),
        "testable_ac_ids": sorted(testable), "excluded_by_profile": excluded,
    }
    budget_report = {k: v for k, v in report.items() if not k.startswith("_")}
    limitations = list(inp.limitations)
    if excluded:
        limitations.append(f"{excluded} case(s) belong to profiles above '{profile}' (not selected)")
    for t in tables:
        if t["unspecified"]:
            limitations.append(f"decision table {t['ac_id']}: {t['unspecified']} of {t['columns']} condition "
                               "combinations are not specified by the criterion (not tested)")
    det = {"profile": profile, "budget": budget_report, "test_cases": final_cases, "cut": cut_out,
           "conflicts": conflicts(inp)}
    doc = {
        "schema_version": 2, "artifact": "test_cases", "project": inp.project, "profile": profile,
        "content_hash": hashlib.sha1(stable_json(det).encode("utf-8")).hexdigest()[:16],
        "generated_at": None, "inputs": dict(inp.present), "limitations": limitations, "budget": budget_report,
        "summary": summary,
        "llm": llm_status or {"status": "skipped", "modules": {}, "added": 0, "rejected_duplicates": rejected_extras},
        "page_hashes": inp.page_hashes(), "test_cases": final_cases, "cut": cut_out, "conflicts": det["conflicts"],
    }
    TestCasesDoc.model_validate(doc)
    return doc


def _count(cases: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in cases:
        out[c[key]] = out.get(c[key], 0) + 1
    return dict(sorted(out.items()))
