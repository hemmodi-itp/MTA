"""
required_fields.py — a positive test that submits a form fills every field the form requires.

A generated "save a product" test filled Name and Price but not the required Category: the page's own validation
stopped the submit, and every assertion after it failed on a correct app. Before rendering, for each positive test:

    the form it submits     the click on a button whose text is a form's submit text, on the page the test opens
    what it filled          fill / select / check steps on keys whose element (`[name=...]` in the locator, or the
                            discovery fingerprint's name attribute) is a field of that form
    missing required fields a fill step with a valid value is inserted before the submit click: the select's first
                            real option, a checked checkbox, a number at its minimum, otherwise a plain text value
                            within the length limits — through the form's own locator key for the field

A required file input cannot be filled this way and is reported, not invented. Negative tests are never touched (a
missing field may be what they test). Pure, no I/O; every insertion is returned for the log.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

FILL_ACTIONS = ("enterText", "clearAndEnterText", "selectDropdownByText", "selectDropdownByValue", "checkCheckbox",
                "uploadFile")
CLICKS = ("click", "doubleClick")
_NAME_IN_CSS = re.compile(r'\[name="([^"]+)"\]')


def _template(path: str) -> str:
    path = re.sub(r"^[a-z]+://[^/]+", "", (path or "").split("?")[0], flags=re.I)
    return re.sub(r"/\d+(?=/|$)", "/{id}", path.rstrip("/") or "/")


def _field_name(entry: Dict[str, Any]) -> Optional[str]:
    m = _NAME_IN_CSS.search(str(entry.get("locator") or ""))
    return m.group(1) if m else (((entry.get("_fingerprint") or {}).get("attrs") or {}).get("name") or None)


def _label(entry: Dict[str, Any]) -> str:
    return str(entry.get("name") or ((entry.get("_fingerprint") or {}).get("name")) or "").strip()


def _valid_step(key: str, fld: Dict[str, Any], known: Any = None) -> Optional[Dict[str, Any]]:
    """`known`: the valid value test design derived for the field (DOM + BRD + observed + code constraints)."""
    c = fld.get("constraints") or {}
    kind = (fld.get("type") or c.get("type") or "text").lower()
    if known not in (None, "") and not isinstance(known, dict) and kind not in ("checkbox", "file", "radio", "hidden"):
        return {"action": "selectDropdownByText" if kind == "select" else "enterText", "locator_key": key,
                "value": str(known)}
    if kind == "select":
        opts = [o for o in c.get("options") or [] if str(o.get("value", "")).strip() and not o.get("disabled")]
        return {"action": "selectDropdownByText", "locator_key": key, "value": opts[0].get("text") or opts[0]["value"]} \
            if opts else None
    if kind == "checkbox":
        return {"action": "checkCheckbox", "locator_key": key}
    if kind in ("file", "radio", "hidden"):
        return None
    if kind == "number":
        return {"action": "enterText", "locator_key": key, "value": str(c.get("min") if c.get("min") not in (None, "") else 1)}
    if kind == "email":
        return {"action": "enterText", "locator_key": key, "value": "qa.user@example.com"}
    lo, hi = int(c.get("minlength") or 0), int(c.get("maxlength") or 0) or None
    value = "Valid test value"
    if hi:
        value = value[:hi]
    if len(value) < lo:
        value = value + "x" * (lo - len(value))
    return {"action": "enterText", "locator_key": key, "value": value}


def complete_required_fields(plan: dict, locator_map: Dict[str, Dict[str, Any]], form_model: Optional[dict],
                             default_page: Optional[str] = None,
                             valid_values: Optional[Dict[Tuple[str, str], Any]] = None) -> Tuple[dict, List[Dict[str, Any]]]:
    """valid_values: (form_id, field name) -> a valid value from test design (tools.test_design.inputs.valid_value_for);
    without one, a value from the DOM constraints alone."""
    forms = [f for f in (form_model or {}).get("forms") or [] if (f.get("method") or "get").lower() != "get"]
    if not forms or not locator_map:
        return plan, []
    plan = copy.deepcopy(plan)
    changes: List[Dict[str, Any]] = []
    for test in plan.get("tests") or []:
        if not isinstance(test, dict) or test.get("type") != "positive":
            continue
        steps = test.get("steps") or []
        pages = [_template(s.get("value") or "") for s in steps
                 if isinstance(s, dict) and s.get("action") == "navigate" and s.get("value")] or \
            ([default_page] if default_page else [])
        for i, st in enumerate(steps):
            if not (isinstance(st, dict) and st.get("action") in CLICKS and st.get("locator_key") in locator_map):
                continue
            text = _label(locator_map[st["locator_key"]])
            cands = [f for f in forms if text and ((f.get("submit") or {}).get("text") or "").strip() == text
                     and (not pages or f.get("url_template") in pages)]
            if len(cands) != 1:
                continue
            form = cands[0]
            filled = {_field_name(locator_map.get(s.get("locator_key")) or {}) for s in steps[:i]
                      if isinstance(s, dict) and s.get("action") in FILL_ACTIONS}
            missing = [fld for fld in form.get("fields") or []
                       if (fld.get("constraints") or {}).get("effective_required") and fld.get("name") not in filled]
            inserts = []
            for fld in missing:
                key = next((k for k, e in locator_map.items() if e.get("_form_id") == form.get("form_id")
                            and _field_name(e) == fld.get("name")), None) or \
                    next((k for k, e in locator_map.items() if _field_name(e) == fld.get("name")
                          and (e.get("_page_url") is None or _template(e["_page_url"]) == form.get("url_template"))), None)
                step = _valid_step(key, fld, (valid_values or {}).get((form.get("form_id"), fld.get("name")))) if key else None
                if step is None:
                    changes.append({"test": test.get("name"), "change": "required field not filled",
                                    "field": fld.get("name"), "reason": "no locator key / no fillable value for it"})
                    continue
                inserts.append(step)
                changes.append({"test": test.get("name"), "change": "required field filled", "field": fld.get("name"),
                                "after": step, "reason": f"{form.get('dom_id') or 'the form'} requires it; the test "
                                                         "left it empty, so its own validation would stop the submit"})
            if inserts:
                test["steps"] = steps[:i] + inserts + steps[i:]
            break                                   # the first submit of the test
    return plan, changes
