"""
assertion_linter.py — Phase 5.3: scores each planned test 0-100 for oracle strength.

Runs on a validated plan (before rendering). Pure, no LLM, no I/O. A test is "weak" below THRESHOLD.

Rules (penalty each; hard rejects zero the score):
  outcome   no assertion about the OUTCOME (only checks the element just acted on)   -40
  title     the only assertions are title checks (not @smoke-reachability)            reject
  negative  negative test needs (error text OR verifyFieldInvalid) AND
            (verifyNoRequest OR a URL check)                                        -35 each half
  xss       XSS / special_chars test needs verifyNoDialog AND verifyNotInjected       -35 each
  sleep     waitForTimeout in the plan                                                reject
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any, Dict, List

THRESHOLD = 70

_ACTING = {
    "click", "doubleClick", "hover", "enterText", "clearAndEnterText", "pressKey", "checkCheckbox",
    "uncheckCheckbox", "selectDropdownByText", "selectDropdownByValue", "scrollIntoView", "uploadFile",
    "dragAndDrop",
}
_TITLE = {"verifyTitle", "verifyTitleContains"}
_URL = {"verifyUrl", "verifyUrlContains"}
# Verifies that describe something other than the element just acted on, whatever their locator.
_ALWAYS_OUTCOME = _URL | {"verifyRequest", "verifyNoRequest", "verifyNoDialog", "verifyNotInjected",
                          "verifyFieldInvalid", "verifyCount"}
_ELEMENT_VERIFY = {"verifyVisible", "verifyHidden", "verifyText", "verifyContainsText", "verifyValue",
                   "verifyEnabled", "verifyDisabled", "verifyChecked"}
_TEXT_VERIFY = {"verifyVisible", "verifyText", "verifyContainsText"}
_XSS_TECHNIQUES = {"special_chars", "xss", "injection", "security"}
_XSS_NAME = re.compile(r"xss|special[ _-]?char|inject|script", re.I)
_XSS_VALUE = re.compile(r"<\s*(script|img|svg|iframe)|\bon\w+\s*=|javascript:", re.I)


def _is_xss(test: dict) -> bool:
    if str(test.get("technique") or "").lower() in _XSS_TECHNIQUES or _XSS_NAME.search(str(test.get("name") or "")):
        return True
    return any(isinstance(st.get("value"), str) and _XSS_VALUE.search(st["value"])
               for st in test.get("steps") or [])


def lint_test(test: dict) -> Dict[str, Any]:
    steps = [s for s in test.get("steps") or [] if isinstance(s, dict)]
    actions = [s.get("action") for s in steps]
    issues: List[str] = []
    score = 100

    if "waitForTimeout" in actions:
        return {"name": test.get("name"), "score": 0, "weak": True,
                "issues": ["sleep: waitForTimeout is a fixed sleep — use waitForElement or a verify* step"]}

    acted = {s.get("locator_key") for s in steps if s.get("action") in _ACTING and s.get("locator_key")}
    acted |= {s.get("target_locator_key") for s in steps if s.get("action") == "dragAndDrop"}
    verifies = [s for s in steps if str(s.get("action", "")).startswith("verify")]

    smoke_reach = "smoke-reachability" in str(test.get("technique") or "") + str(test.get("name") or "")
    if verifies and all(s["action"] in _TITLE for s in verifies) and not smoke_reach:
        return {"name": test.get("name"), "score": 0, "weak": True,
                "issues": ["title: the only assertions are title checks — assert the outcome"]}

    def outcome(s: dict) -> bool:
        a = s["action"]
        if a in _ALWAYS_OUTCOME:
            return True
        return a in _ELEMENT_VERIFY and s.get("locator_key") not in acted

    if not any(outcome(s) for s in verifies) and not (smoke_reach and verifies):
        score -= 40
        issues.append("outcome: no assertion about the outcome — checks only the element just acted on")

    if test.get("type") == "negative":
        has_error = any(s["action"] == "verifyFieldInvalid"
                        or (s["action"] in _TEXT_VERIFY and s.get("locator_key") not in acted) for s in verifies)
        has_no_submit = any(s["action"] == "verifyNoRequest" or s["action"] in _URL for s in verifies)
        if not has_error:
            score -= 35
            issues.append("negative: needs error text (verify* on the error element) or verifyFieldInvalid")
        if not has_no_submit:
            score -= 35
            issues.append("negative: needs verifyNoRequest or a URL-unchanged check (verifyUrl/verifyUrlContains)")

    if _is_xss(test):
        for need in ("verifyNoDialog", "verifyNotInjected"):
            if need not in actions:
                score -= 35
                issues.append(f"xss: payload/special-chars test needs {need}")

    score = max(0, score)
    return {"name": test.get("name"), "score": score, "weak": score < THRESHOLD, "issues": issues}


def lint_plan(plan: dict) -> Dict[str, Any]:
    results = [lint_test(t) for t in plan.get("tests") or []]
    return {
        "results": results,
        "median": median(r["score"] for r in results) if results else 100,
        "weak": [r for r in results if r["weak"]],
    }


def feedback(weak: List[Dict[str, Any]]) -> str:
    """Linter feedback for one regeneration prompt."""
    return "\n".join(f"- test \"{r['name']}\" (score {r['score']}): " + "; ".join(r["issues"]) for r in weak)
