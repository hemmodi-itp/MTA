"""
pairwise.py — combinatorial all-pairs (Phase 3.2), for forms with ≥ 3 parameters where at least two take options
(filters, sort, settings).

all_pairs(params) is a deterministic greedy cover: each new row starts from the first still-uncovered pair, then
every other parameter takes the value that covers the most uncovered pairs (ties → the earlier value). Every pair
of values of every two parameters appears in at least one row (proved in tests).
"""

import itertools
from typing import Any, Dict, List, Sequence, Set, Tuple

from tools.test_design.cases import form_preconditions, form_target, new_case, submit_label
from tools.test_design.inputs import DesignInputs

Pair = Tuple[int, int, int, int]         # (param i, value index a, param j, value index b), i < j


def _all_pairs_set(sizes: Sequence[int]) -> Set[Pair]:
    return {(i, a, j, b) for i, j in itertools.combinations(range(len(sizes)), 2)
            for a in range(sizes[i]) for b in range(sizes[j])}


def all_pairs(params: Sequence[Tuple[str, Sequence[Any]]]) -> List[Dict[str, Any]]:
    names = [n for n, _ in params]
    values = [list(v) for _, v in params]
    if not params or any(not v for v in values):
        return []
    if len(params) == 1:
        return [{names[0]: v} for v in values[0]]
    sizes = [len(v) for v in values]
    uncovered = _all_pairs_set(sizes)
    rows: List[List[int]] = []
    while uncovered:
        i, a, j, b = min(uncovered)
        row = [-1] * len(params)
        row[i], row[j] = a, b
        for k in range(len(params)):
            if row[k] != -1:
                continue
            best, best_gain = 0, -1
            for v in range(sizes[k]):
                gain = 0
                for m in range(len(params)):
                    if m == k or row[m] == -1:
                        continue
                    p = (m, row[m], k, v) if m < k else (k, v, m, row[m])
                    gain += p in uncovered
                if gain > best_gain:
                    best, best_gain = v, gain
            row[k] = best
        for x, y in itertools.combinations(range(len(params)), 2):
            uncovered.discard((x, row[x], y, row[y]))
        rows.append(row)
    return [{names[k]: values[k][v] for k, v in enumerate(r)} for r in rows]


def covered_pairs(rows: List[Dict[str, Any]], params: Sequence[Tuple[str, Sequence[Any]]]) -> bool:
    for (n1, v1), (n2, v2) in itertools.combinations(params, 2):
        for a in v1:
            for b in v2:
                if not any(r[n1] == a and r[n2] == b for r in rows):
                    return False
    return True


def generate(inp: DesignInputs) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for form in inp.forms:
        if form.twin_of or len(form.fields) < 3:
            continue
        params = []
        option_params = 0
        for f in form.fields:
            if f.type == "select" or f.options:
                vals = [o.get("text") or o.get("value") for o in f.options if not o.get("disabled")]
                option_params += 1
            elif f.type in ("search", "text"):
                vals = ["", "e"] if f.type == "search" else ["", "Valid"]
            else:
                continue
            if vals:
                params.append((f.name, vals))
        if option_params < 2 or len(params) < 3:
            continue
        ac_ids = sorted({a for f in form.fields if f.name in dict(params) for a in f.ac_ids})
        for n, row in enumerate(all_pairs(params), 1):
            label = ", ".join(f"{k}={v!r}" for k, v in row.items())
            out.append(new_case(
                key=f"pw|{form.form_id}|{label}", title=f"{form.dom_id or 'form'} combination {n}: {label}",
                technique="pairwise", test_type="positive", level="thorough", target=form_target(form),
                ac_ids=ac_ids, preconditions=form_preconditions(form),
                inputs={k: {"value": v, "value_rule": "pairwise"} for k, v in row.items()},
                steps_outline=[f"set {k} to {v!r}" for k, v in row.items()] + [f"submit ({submit_label(form)})"],
                oracles=[{"type": "no_server_error", "source": "catalog"},
                         {"type": "results_match_filters", "source": "brd"}],
                source="dom", module_id=form.module_id, tags=["combinatorial"], likelihood=0.45,
            ))
    return out
