"""
risk.py — risk-based prioritisation (Phase 3.4): risk = impact × likelihood → P0–P3.

impact      AC priority weight (P0 1.0 · P1 0.75 · P2 0.5 · P3 0.25; no AC 0.4) + 0.1 per risk tag among
            auth / payment / data-loss / PII (capped at 1.0)
likelihood  the generator's base likelihood (an invalid input is likelier to expose a bug than a valid one)
            + 0.04 per input beyond the first (max +0.12) + 0.03 per decision-table condition
            + 0.05 when ≥ 3 transitions touch the page + 0.2 when the page changed since the last design run
            (capped at 1.0)
priority    P0 ≥ 0.7 · P1 ≥ 0.45 · P2 ≥ 0.25 · else P3; a P0 criterion's main-flow case is always P0 (smoke)
"""

from typing import Any, Dict, List

from tools.test_design.inputs import DesignInputs, best_priority, norm_template

IMPACT = {"P0": 1.0, "P1": 0.75, "P2": 0.5, "P3": 0.25}
RISK_TAGS = {"auth", "payment", "data-loss", "pii", "PII"}
THRESHOLDS = (("P0", 0.7), ("P1", 0.45), ("P2", 0.25))


def impact(ac_ids: List[str], inp: DesignInputs) -> float:
    acs = [inp.ac(a) for a in ac_ids if inp.ac(a)]
    if not acs:
        return 0.4
    base = IMPACT[best_priority(a["priority"] for a in acs)]
    tags = {t for a in acs for t in a["risk_tags"] if t in RISK_TAGS}
    return min(1.0, base + 0.1 * len(tags))


def likelihood(case: Dict[str, Any], inp: DesignInputs, changed: set, degree: Dict[str, int]) -> float:
    lk = float(case.get("_likelihood", 0.5))
    lk += 0.04 * min(3, max(0, len(case.get("inputs") or {}) - 1))
    if case["technique"] == "decision_table":
        lk += 0.03 * len(case.get("preconditions") or [])
    t = norm_template((case.get("target") or {}).get("url_template") or "")
    if degree.get(t, 0) >= 3:
        lk += 0.05
    if t in changed:
        lk += 0.2
    return min(1.0, lk)


def priority_for(risk: float) -> str:
    for p, th in THRESHOLDS:
        if risk >= th:
            return p
    return "P3"


def score_all(cases: List[Dict[str, Any]], inp: DesignInputs) -> None:
    changed = inp.changed_pages()
    degree: Dict[str, int] = {}
    for tr in inp.transitions:
        degree[tr.from_t] = degree.get(tr.from_t, 0) + 1
        degree[tr.to_t] = degree.get(tr.to_t, 0) + 1
    for c in cases:
        r = round(impact(c.get("ac_ids") or [], inp) * likelihood(c, inp, changed, degree), 3)
        c["risk_score"] = r
        p = priority_for(r)
        if c["level"] == "smoke":
            p = "P0"
        c["priority"] = p
        if norm_template((c.get("target") or {}).get("url_template") or "") in changed:
            c["tags"] = sorted(set(c["tags"]) | {"changed-page"})
