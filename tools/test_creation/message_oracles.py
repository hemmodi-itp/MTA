"""
message_oracles.py — an expected error message comes from the BRD or from what the app was seen to say, not from
the LLM's wording.

A negative test that asserts "price must be greater than or equal to 0" fails on an app that correctly says "Price
must be zero or more". Before rendering, each text assertion (verifyText / verifyContainsText) on an error area in a
negative test is checked against the known messages — every "quoted" string in the requirements and every visible
error discovery's form probes recorded:

    the text is (part of) a known message, or contains one      kept
    one known message about the field the test changed is       replaced by it
      clearly the closest (similarity >= 0.45, a clear margin)
    otherwise                                                   verifyVisible(error area): the error is shown —
                                                                the wording is not asserted (and reported)

Pure, no I/O. Every change is returned for the log.
"""

from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

TEXT_ACTIONS = ("verifyText", "verifyContainsText")
_QUOTED = re.compile(r'["“]([^"“”\n]{3,160})["”]')
_ERRORISH = re.compile(r"error|alert|invalid|warning|message|feedback", re.I)
MIN_RATIO, MARGIN = 0.45, 0.05


def known_messages(form_model: Optional[dict], requirements: Any) -> List[str]:
    out: List[str] = []

    def add(t: str):
        t = (t or "").strip()
        if t and t not in out:
            out.append(t)
    for form in (form_model or {}).get("forms") or []:
        for p in form.get("probes") or []:
            for e in p.get("visible_errors") or []:
                add(e.get("text"))
        for fld in form.get("fields") or []:
            seen = fld.get("observed_messages") or {}            # {probe kind: {text, source, ...}}
            for m in (seen.values() if isinstance(seen, dict) else seen):
                add(m.get("text") if isinstance(m, dict) else str(m))
    reqs = requirements.get("requirements", []) if isinstance(requirements, dict) else requirements or []
    for r in reqs:
        for ac in r.get("acceptance_criteria") or []:
            for q in _QUOTED.findall(ac.get("statement") or ""):
                add(q)
    return out


def error_keys(locator_map: Dict[str, Dict[str, Any]]) -> set:
    """Locator keys of error areas: the form error containers test design adds (_dynamic), or error-like names."""
    return {k for k, e in (locator_map or {}).items()
            if e.get("_dynamic") or _ERRORISH.search(k) or _ERRORISH.search(str(e.get("description") or ""))}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _known(text: str, messages: Iterable[str]) -> bool:
    """The asserted text is (part of) a message the app shows — toContainText needs exactly that direction."""
    t = _norm(text)
    return bool(t) and any(t in _norm(m) for m in messages)


def _inside(text: str, messages: Iterable[str]) -> Optional[str]:
    """The known message the asserted text wraps ("Product name is required" wraps "Name is required"); a short
    quoted word ("Help") does not count."""
    t = _norm(text)
    found = [m for m in messages if len(m) >= 8 and _norm(m) in t]
    return max(found, key=len) if found else None


def _changed_fields(test: dict) -> List[str]:
    return [str(s.get("locator_key") or "") for s in test.get("steps") or []
            if isinstance(s, dict) and s.get("action") in ("enterText", "clearAndEnterText", "selectDropdownByText",
                                                           "selectDropdownByValue")]


def _closest(text: str, messages: List[str], fields: List[str]) -> Optional[str]:
    """The known message closest to `text` among those naming a field the test changed (else among all)."""
    words = {w for f in fields for w in re.split(r"[_\W]+", f.lower()) if len(w) > 2}
    pool = [m for m in messages if words & set(re.split(r"\W+", m.lower()))] or messages
    scored = sorted(((SequenceMatcher(None, _norm(text), _norm(m)).ratio(), m) for m in pool), reverse=True)
    if not scored or scored[0][0] < MIN_RATIO:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < MARGIN:
        return None
    return scored[0][1]


def ground_messages(plan: dict, messages: List[str], errors: set) -> Tuple[dict, List[Dict[str, Any]]]:
    if not messages or not errors:
        return plan, []
    plan = copy.deepcopy(plan)
    changes: List[Dict[str, Any]] = []
    for test in plan.get("tests") or []:
        if not isinstance(test, dict) or test.get("type") != "negative":
            continue
        fields = _changed_fields(test)
        for i, step in enumerate(test.get("steps") or []):
            if not (isinstance(step, dict) and step.get("action") in TEXT_ACTIONS and step.get("locator_key") in errors):
                continue
            text = str(step.get("value") or "")
            if not text or _known(text, messages):
                continue
            best = _inside(text, messages) or _closest(text, messages, fields)
            if best:
                test["steps"][i] = dict(step, action="verifyContainsText", value=best)
                changes.append({"test": test.get("name"), "change": "message replaced", "before": text, "after": best,
                                "reason": "the expected wording is not one the BRD or the app uses"})
            else:
                test["steps"][i] = {k: v for k, v in step.items() if k != "value"} | {"action": "verifyVisible"}
                changes.append({"test": test.get("name"), "change": "message not asserted", "before": text,
                                "reason": "no known message matches it clearly — only that the error is shown"})
    return plan, changes
