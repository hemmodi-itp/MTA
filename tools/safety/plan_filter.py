"""
plan_filter.py — applies the SafetyPolicy to an action-library test plan.

Called by ScriptGenerationAgent right before render_spec_from_plan (the single
choke point every plan tier passes through). A test is dropped — whole, not just
the offending step, so no later assertion runs against a state that never
happened — when one of its steps (including steps inside a `useFlow` flow from
flows.json, which plan validation never sees) is:

  * a destructive interaction while the policy does not allow destructive
    actions (allow_destructive: false, or environment prod/unspecified), or
  * a `navigate` to an absolute URL outside safety.allowed_hosts.

Every drop is returned as a record so the caller can report it; nothing is
dropped silently.
"""

import copy
from typing import Any, Dict, List, Optional, Tuple

from tools.safety.action_classifier import classify_step
from tools.safety.policy import SafetyPolicy


def _flow_steps(step: Dict[str, Any], flows: Dict[str, Any]) -> List[Dict[str, Any]]:
    flow = flows.get(step.get("flow") or "") if isinstance(flows, dict) else None
    steps = (flow or {}).get("steps") if isinstance(flow, dict) else None
    return [s for s in (steps or []) if isinstance(s, dict)]


def _step_violation(step: Dict[str, Any], policy: SafetyPolicy,
                    locator_map: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    action = step.get("action")
    if action == "navigate":
        target = step.get("value")
        if not policy.url_allowed(target):
            return {"reason": "host_not_allowed", "rule": "safety.allowed_hosts",
                    "detail": str(target), "allowed_hosts": list(policy.allowed_hosts)}
    if policy.destructive_allowed:
        return None
    verdict = classify_step(step, locator_map)
    if verdict.destructive:
        return {"reason": "destructive_action", "category": verdict.category,
                "rule": verdict.rule, "detail": verdict.text}
    return None


def filter_plan(plan: Dict[str, Any], policy: SafetyPolicy,
                locator_map: Optional[Dict[str, Any]] = None,
                flows: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Returns (filtered_plan, dropped). *plan* is not mutated. The filtered plan keeps
    every key of the original and gains `dropped_for_safety` (a list, possibly empty)
    so test_plans.json records what was removed and why.
    """
    locator_map = locator_map or {}
    flows = flows or {}
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for test in plan.get("tests") or []:
        if not isinstance(test, dict):
            continue
        violation = None
        for idx, step in enumerate(test.get("steps") or []):
            if not isinstance(step, dict):
                continue
            candidates = [(step, None)]
            if step.get("action") == "useFlow":
                candidates += [(fs, step.get("flow")) for fs in _flow_steps(step, flows)]
            for cand, flow_name in candidates:
                v = _step_violation(cand, policy, locator_map)
                if v:
                    violation = {**v, "step_index": idx, "action": cand.get("action"),
                                 "locator_key": cand.get("locator_key"), "flow": flow_name}
                    break
            if violation:
                break
        if violation:
            dropped.append({"test": test.get("name"), "type": test.get("type"), **violation})
        else:
            kept.append(test)
    out = copy.deepcopy({k: v for k, v in plan.items() if k != "tests"})
    out["tests"] = kept
    out["dropped_for_safety"] = dropped
    return out, dropped
