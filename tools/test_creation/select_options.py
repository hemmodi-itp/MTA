"""
select_options.py — a generated plan selects only options the <select> really has (discovery's form_model).

Generated data invents choices ("Furniture" for a category select whose options are Books / Electronics / Home);
Playwright then waits for an option that never appears and the test times out on a correct app. Before rendering,
every selectDropdownByText / selectDropdownByValue step on a select discovery saw is checked:

    a real option (text or value, case-insensitive)      kept as is
    not an option, the select is a filler                 the first real option (the placeholder skipped)
    not an option, the select is the very field a         the test is dropped — a value the UI cannot choose is
      negative case targets                               tested through the API (Phase 8), not the browser

Every change is returned for the log. Pure, no I/O.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

SELECT_ACTIONS = ("selectDropdownByText", "selectDropdownByValue")
_NAME_IN_CSS = re.compile(r'\[name="([^"]+)"\]')


def select_options(locator_map: Dict[str, Dict[str, Any]], form_model: Optional[dict]) -> Dict[str, Dict[str, Any]]:
    """locator key -> {field, options: [{value, text}]} for every key that points at a select discovery recorded."""
    fields: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for form in (form_model or {}).get("forms") or []:
        for fld in form.get("fields") or []:
            opts = ((fld.get("constraints") or {}).get("options")) or []
            if opts:
                fields[(form.get("form_id"), fld.get("name"))] = [
                    o for o in opts if isinstance(o, dict) and str(o.get("value", "")).strip() and not o.get("disabled")]
    out: Dict[str, Dict[str, Any]] = {}
    for key, entry in (locator_map or {}).items():
        m = _NAME_IN_CSS.search(str(entry.get("locator") or ""))
        if not m or not entry.get("_form_id"):
            continue
        opts = fields.get((entry["_form_id"], m.group(1)))
        if opts:
            out[key] = {"field": m.group(1), "options": opts}
    return out


def _is_option(value: Any, opts: List[Dict[str, Any]], by_text: bool) -> bool:
    v = str(value if value is not None else "").strip().lower()
    return any(v == str(o.get("text" if by_text else "value", "")).strip().lower()
               or v == str(o.get("value" if by_text else "text", "")).strip().lower() for o in opts)


def ground_selects(plan: dict, options: Dict[str, Dict[str, Any]],
                   cases: Optional[Dict[str, dict]] = None) -> Tuple[dict, List[Dict[str, Any]]]:
    """(plan with every select step on a real option, changes)."""
    if not options:
        return plan, []
    plan = copy.deepcopy(plan)
    changes: List[Dict[str, Any]] = []
    kept_tests = []
    for test in plan.get("tests") or []:
        if not isinstance(test, dict):
            kept_tests.append(test)
            continue
        case = (cases or {}).get(test.get("case_id")) or {}
        target_field = (case.get("target") or {}).get("field")
        drop = None
        for step in test.get("steps") or []:
            if not (isinstance(step, dict) and step.get("action") in SELECT_ACTIONS and step.get("locator_key") in options):
                continue
            info = options[step["locator_key"]]
            by_text = step["action"] == "selectDropdownByText"
            if _is_option(step.get("value"), info["options"], by_text):
                continue
            if test.get("type") == "negative" and target_field == info["field"]:
                drop = (f"{info['field']} has no option {step.get('value')!r}; a value the UI cannot choose is "
                        "tested through the API")
                break
            first = info["options"][0]
            new = first["text"] if by_text else first["value"]
            changes.append({"test": test.get("name"), "change": "option replaced", "field": info["field"],
                            "before": step.get("value"), "after": new,
                            "reason": f"not an option of {info['field']} "
                                      f"({', '.join(str(o.get('text')) for o in info['options'])})"})
            step["value"] = new
        if drop:
            changes.append({"test": test.get("name"), "change": "dropped", "reason": drop})
            continue
        kept_tests.append(test)
    plan["tests"] = kept_tests
    return plan, changes


_NUMERIC = re.compile(r"^\s*-?\d+(\.\d+)?([eE][-+]?\d+)?\s*$")


def number_inputs(locator_map: Dict[str, Dict[str, Any]]) -> set:
    """Locator keys of <input type="number"> elements (discovery fingerprint)."""
    return {k for k, e in (locator_map or {}).items()
            if str(((e.get("_fingerprint") or {}).get("attrs") or {}).get("type") or "").lower() == "number"}


def ground_number_inputs(plan: dict, numbers: set) -> Tuple[dict, List[Dict[str, Any]]]:
    """A browser cannot type text into <input type="number"> (Playwright refuses): a negative test that tries is
    dropped — a non-numeric value is an API rule test — and a positive one gets "1"."""
    if not numbers:
        return plan, []
    plan = copy.deepcopy(plan)
    changes: List[Dict[str, Any]] = []
    kept = []
    for test in plan.get("tests") or []:
        bad = [s for s in (test.get("steps") or []) if isinstance(s, dict) and s.get("action") in ("enterText", "clearAndEnterText")
               and s.get("locator_key") in numbers and str(s.get("value") or "") and not _NUMERIC.match(str(s.get("value")))]
        if bad and test.get("type") == "negative":
            changes.append({"test": test.get("name"), "change": "dropped",
                            "reason": f"{bad[0]['locator_key']} is a number input: the browser cannot hold "
                                      f"{bad[0].get('value')!r} (tested through the API instead)"})
            continue
        for s in bad:
            changes.append({"test": test.get("name"), "change": "number replaced", "before": s.get("value"), "after": "1",
                            "reason": f"{s['locator_key']} is a number input"})
            s["value"] = "1"
        kept.append(test)
    plan["tests"] = kept
    return plan, changes
