"""
select.py — coverage profiles and budgeted selection (Phase 3.5), enforced in code (audit A9).

    1. profile filter: a case belongs to every profile from its `level` upwards (smoke ⊂ standard ⊂ thorough ⊂
       exhaustive); cases above the profile are not generated into the run (counted, not listed);
    2. keep every P0 case;
    3. guarantee the coverage floor: ≥ 1 case per testable AC (smoke: P0 ACs only), plus a negative case for every
       AC that has one in the pool;
    4. add the rest by descending risk while `max_tests` and `max_runtime_minutes` allow;
    5. everything not selected in 4 is cut with reason "budget".
P0 and floor cases are kept even past the budget; the doc then reports `respected: false` (never hidden).
"""

from typing import Any, Dict, List, Tuple

from tools.test_design.config import level_rank

_TYPE_ORDER = {"negative": 0, "boundary": 1, "positive": 2}


def _order(c: Dict[str, Any]):
    return (-c["risk_score"], _TYPE_ORDER.get(c["test_type"], 3), c["id"])


def floor_cases(pool: List[Dict[str, Any]], testable_ac_ids: List[str]) -> List[str]:
    """Smallest deterministic set: for each AC the highest-risk case covering it, and the highest-risk negative."""
    chosen: List[str] = []
    ranked = sorted(pool, key=_order)
    for ac in testable_ac_ids:
        cover = [c for c in ranked if ac in (c.get("ac_ids") or [])]
        if not cover:
            continue
        # prefer the AC's own main-flow case, then anything
        main = next((c for c in cover if c["technique"] == "use_case" and "floor" in c.get("tags", [])
                     and c["test_type"] != "negative"), None) or cover[0]
        if main["id"] not in chosen:
            chosen.append(main["id"])
        neg = next((c for c in cover if c["test_type"] == "negative"), None)
        if neg is not None and neg["id"] not in chosen:
            chosen.append(neg["id"])
    return chosen


def select(cases: List[Dict[str, Any]], profile: str, budget: Dict[str, Any],
           testable_ac_ids: List[str], smoke_ac_ids: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """(selected, cut, budget_report). `cut` entries carry reason "budget"."""
    rank = level_rank(profile)
    pool = [c for c in cases if level_rank(c["level"]) <= rank]
    excluded = len(cases) - len(pool)
    by_id = {c["id"]: c for c in pool}
    floor_ids = floor_cases(pool, smoke_ac_ids if profile == "smoke" else testable_ac_ids)
    p0 = [c["id"] for c in sorted(pool, key=_order) if c["priority"] == "P0"]
    must = list(dict.fromkeys(p0 + floor_ids))
    max_tests = int(budget["max_tests"])
    max_secs = float(budget["max_runtime_minutes"]) * 60.0
    selected_ids: List[str] = list(must)
    secs = sum(by_id[i]["est_seconds"] for i in selected_ids)
    cut: List[Dict[str, Any]] = []
    for c in sorted(pool, key=_order):
        if c["id"] in by_id and c["id"] in selected_ids:
            continue
        if len(selected_ids) < max_tests and secs + c["est_seconds"] <= max_secs:
            selected_ids.append(c["id"])
            secs += c["est_seconds"]
        else:
            cut.append(dict(c, _cut_reason="budget",
                            _cut_detail=f"max_tests={max_tests}, max_runtime_minutes={budget['max_runtime_minutes']}"))
    selected = [by_id[i] for i in selected_ids]
    report = {
        "max_tests": max_tests, "max_runtime_minutes": float(budget["max_runtime_minutes"]),
        "selected": len(selected), "est_runtime_minutes": round(secs / 60.0, 2),
        "respected": len(selected) <= max_tests and secs <= max_secs,
        "p0_over_budget": len(must) > max_tests or sum(by_id[i]["est_seconds"] for i in must) > max_secs,
        "_excluded_by_profile": excluded,
    }
    return selected, cut, report
