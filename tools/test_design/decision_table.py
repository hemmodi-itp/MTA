"""
decision_table.py — decision tables (Phase 3.2).

The LLM only extracts conditions, actions and rules from AC text ("if / when / unless / only if"); the table is
built and collapsed deterministically here:

    build(conditions, rules)  every combination of condition values (True before False), each mapped to the
                              action of the FIRST rule whose `when` matches (None = the AC does not say)
    collapse(columns)         repeatedly merges two columns with the same action that differ in exactly one
                              condition into one column with "-" (don't care) there, until nothing merges
    generate(inp, hints)      one test case per collapsed column with a known action
"""

import itertools
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.test_design.cases import new_case
from tools.test_design.inputs import DesignInputs

DC = "-"
Column = Tuple[Tuple[Any, ...], Optional[str]]          # (condition values, action)
_NEGATIVE_WORDS = ("reject", "error", "denied", "deny", "invalid", "not ", "no ", "already", "blocked", "refuse",
                   "fail", "cannot", "redirect", "403", "401", "disabled", "empty")


def build(conditions: Sequence[str], rules: Sequence[Dict[str, Any]]) -> List[Column]:
    cols: List[Column] = []
    for values in itertools.product((True, False), repeat=len(conditions)):
        action = None
        for rule in rules:
            when = rule.get("when") or {}
            if all(when.get(c) is None or when.get(c) == v for c, v in zip(conditions, values)) and \
                    any(c in when for c in conditions):
                action = rule.get("then")
                break
        cols.append((tuple(values), action))
    return cols


def _merge(a: Tuple[Any, ...], b: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) != 1 or DC in (a[diff[0]], b[diff[0]]):
        return None
    out = list(a)
    out[diff[0]] = DC
    return tuple(out)


def _key(col: Column):
    return (tuple({True: 0, False: 1, DC: 2}[v] for v in col[0]), col[1] or "")


def collapse(columns: Sequence[Column]) -> List[Column]:
    cols = sorted(set(columns), key=_key)
    changed = True
    while changed:
        changed = False
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                (va, aa), (vb, ab) = cols[i], cols[j]
                if aa != ab:
                    continue
                merged = _merge(va, vb)
                if merged is not None:
                    rest = [c for k, c in enumerate(cols) if k not in (i, j)]
                    cols = sorted(set(rest + [(merged, aa)]), key=_key)
                    changed = True
                    break
            if changed:
                break
    return cols


def covers(collapsed: Sequence[Column], full: Sequence[Column]) -> bool:
    """Every fully specified column is represented by exactly one collapsed column with the same action."""
    for values, action in full:
        hits = [a for v, a in collapsed if all(x == DC or x == y for x, y in zip(v, values))]
        if len(hits) != 1 or hits[0] != action:
            return False
    return True


def _render(conditions: Sequence[str], values: Sequence[Any]) -> str:
    parts = [f"{c}={'Y' if v is True else 'N'}" for c, v in zip(conditions, values) if v != DC]
    return ", ".join(parts) or "any"


def generate(inp: DesignInputs, hints: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(cases, tables) — tables are recorded in the doc for review (with unspecified combinations counted)."""
    cases: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    for h in sorted(hints, key=lambda h: h["ac_id"]):
        ac = inp.ac(h["ac_id"])
        if ac is None or ac["testability"] != "ui":
            continue
        conds = list(dict.fromkeys(h["conditions"]))[:6]
        if len(conds) < 2:
            continue
        full = build(conds, h["rules"])
        unspecified = sum(1 for _, a in full if a is None)
        collapsed = collapse([c for c in full if c[1] is not None])
        tables.append({"ac_id": ac["id"], "conditions": conds, "columns": len(full), "collapsed": len(collapsed),
                       "unspecified": unspecified})
        level = "standard" if ac["priority"] in ("P0", "P1") else "thorough"
        for values, action in collapsed:
            when = _render(conds, values)
            negative = any(w in f" {action.lower()} " for w in _NEGATIVE_WORDS)
            cases.append(new_case(
                key=f"dt|{ac['id']}|{when}|{action}", title=f"{ac['id']} rule: {when} → {action}",
                technique="decision_table", test_type="negative" if negative else "positive", level=level,
                target={"kind": "ac"}, ac_ids=[ac["id"]],
                preconditions=[f"{c} is {'true' if v is True else 'false'}" for c, v in zip(conds, values) if v != DC],
                steps_outline=["establish the conditions above", "perform the action the criterion describes"],
                oracles=[{"type": "outcome", "expected": action, "source": "llm_inferred"}], source="brd+llm_inferred",
                confidence=0.8, module_id=ac["module_id"], tags=["dt"], likelihood=0.5 + 0.05 * len(conds),
            ))
    return cases, tables
