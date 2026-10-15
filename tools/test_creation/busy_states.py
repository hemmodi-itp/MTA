"""
busy_states.py — "the button is disabled while saving" is checked while the save is in flight.

A plan that clicks a submit button and then asserts verifyDisabled on it fails on a correct, fast app: the disabled
state lasts only until the response arrives (and the button's label may change to "Saving..." meanwhile, so a
role+name locator no longer finds it). The pair click(K) / doubleClick(K) followed directly by verifyDisabled(K) is
rewritten to the one runtime action that can observe it, verifyBusyWhileSubmitting(K) (it holds the request while it
checks). Pure; every rewrite is returned for the log.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple


def ground_busy_states(plan: dict) -> Tuple[dict, List[Dict[str, Any]]]:
    plan = copy.deepcopy(plan)
    changes: List[Dict[str, Any]] = []
    for test in plan.get("tests") or []:
        steps = test.get("steps") if isinstance(test, dict) else None
        if not steps:
            continue
        out: List[Any] = []
        i = 0
        while i < len(steps):
            a, b = steps[i], steps[i + 1] if i + 1 < len(steps) else None
            if isinstance(a, dict) and isinstance(b, dict) and a.get("action") in ("click", "doubleClick") \
                    and b.get("action") == "verifyDisabled" and a.get("locator_key") \
                    and a.get("locator_key") == b.get("locator_key"):
                busy = {"action": "verifyBusyWhileSubmitting", "locator_key": a["locator_key"]}
                if b.get("message"):
                    busy["message"] = b["message"]
                out.append(busy)
                changes.append({"test": test.get("name"), "change": "busy state", "locator_key": a["locator_key"],
                                "reason": f"{a['action']} + verifyDisabled: the disabled state only lasts while the "
                                          "submit is in flight — checked with the request held"})
                i += 2
                continue
            out.append(a)
            i += 1
        test["steps"] = out
    return plan, changes
