"""
use_case.py — use-case / journey testing (Phase 3.2), driven by the acceptance criteria and business scenarios.

    per testable AC     the main flow it describes (positive), or — when the criterion itself describes a
                        rejection — that exception flow (negative)          [smoke for P0 positives, else standard]
                        plus the exception flow that violates it, when it has a negative path         [standard]
    per scenario        the end-to-end journey across its pages (main flow) [standard if it holds a P0 AC]

These cases are the coverage floor of every profile (≥ 1 case per testable AC, plus a negative where one exists).
Whether an AC has a negative path comes from the LLM hint when present, otherwise from the wording.
"""

import re
from typing import Any, Dict, List, Optional

from tools.test_design.cases import new_case
from tools.test_design.constraints import message_kind, quoted_messages
from tools.test_design.inputs import DesignInputs

_NEG_POLARITY = re.compile(
    r"\b(reject\w*|denied|forbidden|40[13]|wrong|unknown|invalid|any other|anything else|does not|do not|"
    r"must not|is not|never executed|cannot|redirects? to the login|(?<!non-)empty cart|"
    r"already applied|over \d+\s*[KMG]B|more than)\b", re.I)
# "without signing in" describes anonymous ACCESS (positive); a rejection is caught by "redirects to the login".
_HAS_NEG_PATH = re.compile(
    r"\b(required|must|only|at most|at least|between|from \d+ to|one of|once|valid|exactly|accepted|available to)\b",
    re.I)


def is_negative(statement: str) -> bool:
    return bool(_NEG_POLARITY.search(statement or ""))


def has_negative_path(statement: str) -> bool:
    return bool(_HAS_NEG_PATH.search(statement or "")) and not is_negative(statement)


def _oracles(statement: str, negative: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in quoted_messages(statement):
        if "<" in m:
            out.append({"type": "text_pattern", "pattern": re.sub(r"<[^>]+>", "*", m), "source": "brd"})
        elif message_kind(m) or negative:
            out.append({"type": "error_text" if negative else "text_visible", "contains": m, "source": "brd"})
        else:
            out.append({"type": "text_visible", "contains": m, "source": "brd"})
    out.append({"type": "criterion", "statement": statement, "source": "brd"})
    return out


def _scenario_for(inp: DesignInputs, ac_id: str) -> Optional[Dict[str, Any]]:
    for s in inp.scenarios:
        if ac_id in (s.get("ac_ids") or []):
            return s
    return None


def _steps(s: Optional[Dict[str, Any]], statement: str) -> List[str]:
    if s:
        steps = [st if isinstance(st, str) else (st.get("description") or st.get("action") or str(st))
                 for st in (s.get("steps") or [])]
        steps = [str(x)[:200] for x in steps if x][:8]
        if steps:
            return steps
    return [f"perform what the criterion describes: {statement[:200]}"]


def generate(inp: DesignInputs, negative_hints: Optional[Dict[str, bool]] = None) -> List[Dict[str, Any]]:
    negative_hints = negative_hints or {}
    out: List[Dict[str, Any]] = []
    for ac in inp.testable_acs():
        stmt = ac["statement"]
        neg = is_negative(stmt)
        scen = _scenario_for(inp, ac["id"])
        steps = _steps(scen, stmt)
        short = re.sub(r"\s+", " ", stmt)[:110]
        out.append(new_case(
            key=f"uc|ac|{ac['id']}|main", title=f"{ac['id']} {'exception' if neg else 'main'} flow: {short}",
            technique="use_case", test_type="negative" if neg else "positive",
            level="smoke" if ac["priority"] == "P0" and not neg else "standard",
            target={"kind": "ac"}, ac_ids=[ac["id"]], steps_outline=steps, oracles=_oracles(stmt, neg),
            source="brd", module_id=ac["module_id"], tags=["floor"], likelihood=0.6,
            preconditions=[f"scenario {scen['scenario_id']}"] if scen else [],
        ))
        wants_negative = negative_hints.get(ac["id"], has_negative_path(stmt)) and not neg
        if wants_negative:
            out.append(new_case(
                key=f"uc|ac|{ac['id']}|exception",
                title=f"{ac['id']} exception flow: violate \"{short}\"",
                technique="use_case", test_type="negative", level="standard", target={"kind": "ac"},
                ac_ids=[ac["id"]], steps_outline=steps[:-1] + ["do the step with input or state that breaks the rule"]
                if len(steps) > 1 else ["break the rule the criterion states"],
                oracles=[{"type": "criterion_violation_handled", "statement": stmt, "source": "brd"}],
                source="brd", module_id=ac["module_id"], tags=["floor"], likelihood=0.7,
                preconditions=[f"scenario {scen['scenario_id']}"] if scen else [],
            ))
    for s in inp.scenarios:
        ac_ids = [a for a in (s.get("ac_ids") or []) if inp.ac(a) and inp.ac(a)["testability"] == "ui"]
        if len(ac_ids) < 2:
            continue
        p0 = any(inp.ac(a)["priority"] == "P0" for a in ac_ids)
        out.append(new_case(
            key=f"uc|journey|{s.get('scenario_id')}", title=f"Journey: {s.get('title') or s.get('scenario_id')}",
            technique="use_case", test_type="positive", level="standard" if p0 else "thorough",
            target={"kind": "ac"}, ac_ids=ac_ids, steps_outline=_steps(s, s.get("title") or ""),
            oracles=[{"type": "journey_completes", "source": "brd"}], source="brd", module_id=s.get("module_id"),
            tags=["journey"], likelihood=0.5,
        ))
    return out
