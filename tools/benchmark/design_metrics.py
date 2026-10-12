"""
design_metrics.py — Phase 3 benchmark metrics computed on test_cases.json (no execution needed).

    bug_targeting(doc, bugs)   for each seeded bug: the selected cases that TARGET it — a case linked to the bug's
                               affected AC (or one of its child ACs) whose technique can expose that category of
                               bug. Acceptance (plan Phase 3): every validation and state-machine bug is targeted.
    design_summary(doc, bugs)  coverage, budget, technique mix and targeting in one dict for the report.

Three honesty levels, all reported side by side:
  * any technique         — includes `use_case`, which restates each AC and therefore always "covers" it;
  * by technique          — excludes use_case / llm_domain: what EP, BVA, state transition, role matrix … add;
  * implemented (specs)   — only cases a generated plan actually implements (`case_id` in test_plans.json).
A targeted bug is not yet a detected bug: detection needs the test to run and fail (score.py).
"""

from typing import Any, Dict, Iterable, List, Optional, Set

# Techniques that can expose each bug category (others may still hit it by chance; this is the design intent).
TECHNIQUES_FOR = {
    "validation_boundary": {"bva"},
    "validation_numeric": {"bva", "ep"},
    "required_validation": {"ep", "bva", "use_case"},
    "upload_validation": {"ep", "bva", "error_guessing", "use_case"},
    "state_machine": {"state_transition", "use_case", "decision_table"},
    "server_client_mismatch": {"ep", "bva"},
    "business_rule": {"decision_table", "use_case", "llm_domain"},
    "authorization_role": {"role_matrix", "use_case"},
    "authorization_idor": {"role_matrix", "use_case"},
    "persistence": {"crud", "use_case"},
    "concurrency": {"error_guessing", "state_transition", "use_case"},
    "error_handling": {"error_guessing", "use_case", "pairwise"},
    "search": {"ep", "error_guessing", "use_case"},
    "calculation": {"use_case", "decision_table", "llm_domain"},
    "security_xss": {"error_guessing", "use_case"},
    "navigation": {"state_transition", "use_case"},
    "session": {"use_case", "state_transition", "role_matrix"},
    "wrong_message": {"use_case", "ep"},
    "sorting": {"use_case", "pairwise"},
    "pagination": {"use_case", "pairwise", "state_transition"},
    # accessibility / performance: non-functional (Phase 7) — no Phase 3 technique targets them
}
# The Phase 3 acceptance criterion covers these categories ("every seeded validation and state-machine bug").
ACCEPTANCE_CATEGORIES = ("validation_boundary", "validation_numeric", "required_validation", "upload_validation",
                         "state_machine")
AC_RESTATING = {"use_case", "llm_domain"}


def _covers(case_acs: List[str], affected: str) -> bool:
    return any(a == affected or a.startswith(affected + ".") for a in case_acs)


def bug_targeting(doc: Dict[str, Any], bugs: List[Dict[str, Any]], exclude: Iterable[str] = (),
                  only_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    out = []
    exclude = set(exclude)
    cases = [c for c in doc.get("test_cases") or [] if c["technique"] not in exclude
             and (only_ids is None or c["id"] in only_ids)]
    for bug in bugs:
        affected = bug.get("affected_ac") or ""
        allowed = TECHNIQUES_FOR.get(bug.get("category"), set())
        hits = [c for c in cases if _covers(c.get("ac_ids") or [], affected) and c["technique"] in allowed]
        any_ac = [c for c in cases if _covers(c.get("ac_ids") or [], affected)]
        out.append({
            "id": bug["id"], "category": bug.get("category"), "affected_ac": affected,
            "in_acceptance": bug.get("category") in ACCEPTANCE_CATEGORIES,
            "targeted": bool(hits), "targeting_cases": [c["id"] for c in hits][:10],
            "techniques": sorted({c["technique"] for c in hits}),
            "cases_on_ac": len(any_ac),
        })
    return out


def _coverage(doc: Dict[str, Any], exclude: Iterable[str] = (), only_ids: Optional[Set[str]] = None) -> Optional[float]:
    testable = set((doc.get("summary") or {}).get("testable_ac_ids") or [])
    if not testable:
        return None
    exclude = set(exclude)
    acs = {a for c in doc.get("test_cases") or [] if c["technique"] not in exclude
           and (only_ids is None or c["id"] in only_ids) for a in c.get("ac_ids") or []}
    return round(100.0 * len(acs & testable) / len(testable), 1)


def implemented_case_ids(plans: Dict[str, Any]) -> Set[str]:
    return {t["case_id"] for p in (plans or {}).values() if isinstance(p, dict)
            for t in p.get("tests") or [] if isinstance(t, dict) and t.get("case_id")}


def design_summary(doc: Dict[str, Any], bugs: List[Dict[str, Any]],
                   implemented: Optional[Set[str]] = None) -> Dict[str, Any]:
    def acc(rows):
        rows = [t for t in rows if t["in_acceptance"]]
        return sum(t["targeted"] for t in rows), len(rows)

    targeting = bug_targeting(doc, bugs)
    by_tech = bug_targeting(doc, bugs, exclude=AC_RESTATING)
    s, b = doc.get("summary") or {}, doc.get("budget") or {}
    out = {
        "profile": doc.get("profile"),
        "selected": s.get("selected"), "generated": s.get("generated"), "cut": s.get("cut"),
        "excluded_by_profile": s.get("excluded_by_profile"),
        "ac_coverage_pct": s.get("ac_coverage_pct"), "acs_without_case": s.get("acs_without_case"),
        "ac_coverage_pct_by_technique": _coverage(doc, exclude=AC_RESTATING),
        "by_technique": s.get("by_technique"), "by_priority": s.get("by_priority"),
        "budget_respected": b.get("respected"), "est_runtime_minutes": b.get("est_runtime_minutes"),
        "bugs_targeted": sum(t["targeted"] for t in targeting), "bugs_total": len(targeting),
        "acceptance_bugs_targeted": acc(targeting)[0], "acceptance_bugs_total": acc(targeting)[1],
        "acceptance_bugs_targeted_by_technique": acc(by_tech)[0],
        "conflicts": len(doc.get("conflicts") or []),
        "targeting": [dict(t, techniques_excl_use_case=bt["techniques"]) for t, bt in zip(targeting, by_tech)],
    }
    if implemented is not None:
        impl = bug_targeting(doc, bugs, only_ids=implemented)
        out.update({
            "cases_implemented": len(implemented & {c["id"] for c in doc.get("test_cases") or []}),
            "ac_coverage_pct_implemented": _coverage(doc, only_ids=implemented),
            "acceptance_bugs_targeted_implemented": acc(impl)[0],
            "bugs_targeted_implemented": sum(t["targeted"] for t in impl),
        })
    return out
