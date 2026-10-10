"""
normalize.py — coerce the Agent-Evaluation BRD step's LLM requirement rows into clean REQ-xx / AC-xx.y rows.

Moved here unchanged from agents/comprehension/brd_builder/agent.py (Phase 1.4, shared core); the agent module
re-exports every name, so callers, tests and monkeypatch targets keep working. Phase 1 adds deterministic,
additive enrichment (design decision D3) — it changes no existing field, score or DB column:
  requirement:  risk_tags, priority_p (P0-P3)
  criterion:    risk_tags, priority_p, atomic, atomicity_issues
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from tools.requirements import atomicity
from tools.requirements.brd_index import BrdIndex
from tools.requirements.classify import from_agent_eval_priority, resolve_priority, risk_tags_for

# 40, not 25: real BRDs commonly state 30-50 requirements, and dropping the tail silently made the
# compliance denominator wrong. Downstream cost is bounded elsewhere (the runtime test budget, the
# process-wide LLM limiter and response cache), so the extra requirements cost code-trace calls only.
MAX_REQUIREMENTS = 40
MAX_CRITERIA = 8
SELF_GENERATED_MAX_CONFIDENCE = 0.6
UNGROUNDED_FACTOR = 0.6
_PRIORITIES = {"high", "medium", "low"}


_KINDS = {"functional", "non_functional", "security", "performance", "compliance", "ux", "data"}
_VERIFIABILITY = {"static", "runtime", "both", "non_technical"}
_ORACLES = {"deterministic", "semantic", "static"}


def _origin(brd_source: str) -> Tuple[str, float]:
    """A BRD's provenance decides whether its requirements may be scored (see design doc, section 8)."""
    if brd_source == "repository":
        return "brd", 1.0
    if brd_source == "generated_live":
        # observed on the live app: intent, but our inference — and self-generated, so capped
        return "inferred", SELF_GENERATED_MAX_CONFIDENCE
    return "descriptive", 0.3     # written from the code: describes the implementation, never scored


def normalize_requirements(raw: List[Any], index: Optional[BrdIndex] = None, brd_source: str = "repository",
                           limitations: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], int]:
    """Coerce LLM output into clean rows with REQ-xx / AC-xx.y codes, dropping untraceable ones.

    Adds per criterion: verifiability (defaults to the requirement's), grounded (token overlap with the BRD),
    confidence, self_generated. Caps (MAX_REQUIREMENTS, MAX_CRITERIA) are recorded in `limitations`.
    """
    origin, confidence = _origin(brd_source)
    self_generated = brd_source != "repository"
    if self_generated:
        confidence = min(confidence, SELF_GENERATED_MAX_CONFIDENCE)
    out: List[Dict[str, Any]] = []
    dropped = overflow = 0
    criteria_cut: List[str] = []
    for item in raw:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        quote = re.sub(r"\s+", " ", str(item.get("source_quote") or "")).strip()
        if index is not None and not (index.grounded(quote) or index.grounded(str(item.get("description") or ""))):
            dropped += 1
            continue
        if len(out) >= MAX_REQUIREMENTS:
            overflow += 1
            continue
        n = len(out) + 1
        priority = str(item.get("priority") or "medium").lower()
        kind = str(item.get("kind") or "functional").lower().replace("-", "_")
        verif = str(item.get("verifiability") or "both").lower()
        verif = verif if verif in _VERIFIABILITY else "both"
        inferred_note = "(inferred)" in (quote + str(item.get("description") or "")).lower()
        req_conf = round(confidence * (0.66 if inferred_note else 1.0), 2)
        criteria = []
        raw_criteria = [c for c in item.get("acceptance_criteria") or []
                        if re.sub(r"\s+", " ", str((c.get("statement") if isinstance(c, dict) else c) or "")).strip()]
        if len(raw_criteria) > MAX_CRITERIA:
            criteria_cut.append(f"REQ-{n:02d} ({len(raw_criteria)})")
        for c in raw_criteria[:MAX_CRITERIA]:
            statement = re.sub(r"\s+", " ", str((c.get("statement") if isinstance(c, dict) else c) or "")).strip()
            hint = str(c.get("oracle_hint") if isinstance(c, dict) else "semantic").lower()
            cv = str((c.get("verifiability") if isinstance(c, dict) else None) or verif).lower()
            criteria.append(_criterion(f"AC-{n:02d}.{len(criteria) + 1}", statement, hint if hint in _ORACLES else "semantic",
                                       cv if cv in _VERIFIABILITY else verif, index, req_conf, self_generated))
        if not criteria:  # a requirement with no stated criteria is checked against its own statement
            criteria = [_criterion(f"AC-{n:02d}.1", str(item.get("description") or item["title"]).strip(), "semantic",
                                   verif, index, req_conf, self_generated)]
        out.append({
            "code": f"REQ-{n:02d}",
            "title": re.sub(r"\s+", " ", str(item["title"])).strip()[:300],
            "description": str(item.get("description") or "").strip(),
            "priority": priority if priority in _PRIORITIES else "medium",
            "kind": kind if kind in _KINDS else "functional",
            "verifiability": verif,
            "origin": origin,
            "confidence": req_conf,
            "self_generated": self_generated,
            "section": str(item.get("section") or "").strip()[:60] or None,
            "source_quote": quote[:600] or None,
            "criteria": criteria,
            "acceptance_criteria": [c["statement"] for c in criteria],  # kept for older readers
        })
        _enrich(out[-1])
    if limitations is not None:
        if overflow:
            limitations.append(f"The BRD states more than {MAX_REQUIREMENTS} traceable requirements; {overflow} beyond the "
                               f"first {MAX_REQUIREMENTS} were not evaluated.")
        if criteria_cut:
            limitations.append(f"Only the first {MAX_CRITERIA} acceptance criteria per requirement were evaluated; "
                               f"cut: {', '.join(criteria_cut[:10])}{'…' if len(criteria_cut) > 10 else ''}.")
    return out, dropped


def _criterion(code: str, statement: str, hint: str, verifiability: str, index: Optional[BrdIndex],
               req_conf: float, self_generated: bool) -> Dict[str, Any]:
    grounded = True if index is None else index.criterion_grounded(statement)
    conf = req_conf if grounded else round(req_conf * UNGROUNDED_FACTOR, 2)
    return {"code": code, "statement": statement[:1000], "oracle_hint": hint, "verifiability": verifiability,
            "grounded": grounded, "confidence": conf, "self_generated": self_generated}


def _enrich(req: Dict[str, Any]) -> None:
    """Phase 1 (D3): deterministic risk tags, P0-P3 priority and atomicity flags, added beside existing fields."""
    req_tags = risk_tags_for(f"{req['title']} {req['description']}")
    req["risk_tags"] = req_tags
    req["priority_p"] = resolve_priority(None, from_agent_eval_priority(req["priority"]), req_tags)[0]
    for c in req["criteria"]:
        tags = risk_tags_for(f"{c['statement']} {req['title']}")
        c["risk_tags"] = tags
        c["priority_p"] = resolve_priority(None, from_agent_eval_priority(req["priority"]), tags)[0]
        c["atomic"], c["atomicity_issues"] = atomicity.check(c["statement"])
