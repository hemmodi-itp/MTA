"""
assertion_linter.py — Phase 5.3: scores each planned test 0-100 for oracle strength.

Runs on a validated plan (before rendering). Pure, no LLM, no I/O. A test is "weak" below THRESHOLD.

Rules (penalty each; hard rejects zero the score):
  outcome   no assertion about the OUTCOME (only checks the element just acted on)   -40
  title     the only assertions are title checks (not @smoke-reachability)            reject
  negative  negative test needs (error text / verifyFieldInvalid / verifyValidationMessage) AND
            (verifyNoRequest / a URL check / verifyCountChangedBy 0)                  -35 each half
  xss       XSS / special_chars test needs verifyNoDialog AND verifyNotInjected       -35 each
  submit    positive test that fills a form and submits it (not search/filter/sort,   -35
            not an xss test) needs a UI success signal
            AND backend evidence (verifyRequest 2xx/3xx / reloadAndVerify / verifyApiState /
            verifyCountChangedBy != 0)                                                -35
  sleep     waitForTimeout in the plan                                                reject

The steps inside a reloadAndVerify are counted as the test's own assertions.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any, Dict, List

THRESHOLD = 70

_ACTING = {
    "click", "doubleClick", "verifyBusyWhileSubmitting", "hover", "enterText", "clearAndEnterText", "pressKey", "checkCheckbox",
    "uncheckCheckbox", "selectDropdownByText", "selectDropdownByValue", "scrollIntoView", "uploadFile",
    "dragAndDrop",
}
_FILL = {"enterText", "clearAndEnterText", "selectDropdownByText", "selectDropdownByValue", "checkCheckbox",
         "uploadFile"}
_TITLE = {"verifyTitle", "verifyTitleContains"}
_URL = {"verifyUrl", "verifyUrlContains"}
# Verifies that describe something other than the element just acted on, whatever their locator.
_ALWAYS_OUTCOME = _URL | {"verifyRequest", "verifyNoRequest", "verifyNoDialog", "verifyNotInjected",
                          "verifyFieldInvalid", "verifyCount", "verifyValidationMessage", "verifyCountChangedBy",
                          "verifyApiState", "verifyResponseSchema", "verifyStorage", "verifyDownload",
                          "verifyBusyWhileSubmitting",
                          "verifyNewTab"}
_ELEMENT_VERIFY = {"verifyVisible", "verifyHidden", "verifyText", "verifyContainsText", "verifyValue",
                   "verifyEnabled", "verifyDisabled", "verifyChecked", "verifyAriaSnapshot"}
_TEXT_VERIFY = {"verifyVisible", "verifyText", "verifyContainsText"}
# Backend-level checks: they prove the request/state, not what the user sees.
_BACKEND = {"verifyRequest", "verifyNoRequest", "verifyApiState", "verifyResponseSchema", "verifyStorage"}
_XSS_TECHNIQUES = {"special_chars", "xss", "injection", "security"}
_XSS_NAME = re.compile(r"xss|special[ _-]?char|(?<!fault[ _-])inject|script", re.I)   # not "fault injection"
_XSS_VALUE = re.compile(r"<\s*(script|img|svg|iframe)|\bon\w+\s*=|javascript:", re.I)
# A search / filter / sort form reads data; the submit rule is for submissions that change state.
_READ_ONLY = re.compile(r"search|filter|sort|find|query|lookup", re.I)


def _is_xss(test: dict, steps: List[dict]) -> bool:
    if str(test.get("technique") or "").lower() in _XSS_TECHNIQUES or _XSS_NAME.search(str(test.get("name") or "")):
        return True
    return any(isinstance(st.get("value"), str) and _XSS_VALUE.search(st["value"]) for st in steps)


def _flatten(steps: List[Any]) -> List[dict]:
    out: List[dict] = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        out.append(s)
        if s.get("action") == "reloadAndVerify":
            out += [x for x in s.get("steps") or [] if isinstance(x, dict)]
    return out


def _is_success(status: Any) -> bool:
    """2xx, or 3xx (a server-rendered form answers a successful POST with a redirect)."""
    if status is None:
        return False
    text = str(status).strip().lower()
    return text in ("2xx", "3xx", "success") or (text.isdigit() and 200 <= int(text) < 400)


def _is_submit(test: dict, steps: List[dict]) -> bool:
    """A state-changing form submission: a field is filled, then something is clicked / Enter is pressed.
    Search/filter/sort forms (by test name or the filled/clicked keys) are not submissions."""
    if _READ_ONLY.search(str(test.get("name") or "")):
        return False
    filled = False
    for s in steps:
        a = s.get("action")
        if _READ_ONLY.search(str(s.get("locator_key") or "")):
            continue
        if a in _FILL:
            filled = True
        elif filled and (a == "click" or (a == "pressKey" and str(s.get("value", "")).lower() == "enter")):
            return True
    return False


def lint_test(test: dict) -> Dict[str, Any]:
    steps = _flatten(test.get("steps") or [])
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
        has_error = any(s["action"] in ("verifyFieldInvalid", "verifyValidationMessage")
                        or (s["action"] in _TEXT_VERIFY and s.get("locator_key") not in acted) for s in verifies)
        has_no_submit = any(s["action"] == "verifyNoRequest" or s["action"] in _URL
                            or (s["action"] == "verifyCountChangedBy" and s.get("delta") == 0) for s in verifies)
        if not has_error:
            score -= 35
            issues.append("negative: needs error text (verify* on the error element), verifyFieldInvalid "
                          "or verifyValidationMessage")
        if not has_no_submit:
            score -= 35
            issues.append("negative: needs verifyNoRequest, a URL-unchanged check (verifyUrl/verifyUrlContains) "
                          "or verifyCountChangedBy 0")

    xss = _is_xss(test, steps)
    if test.get("type") == "positive" and not xss and _is_submit(test, steps):
        ui_signal = any(outcome(s) and s["action"] not in _BACKEND for s in verifies)
        backend = any((s["action"] == "verifyRequest" and _is_success(s.get("status")))
                      or s["action"] == "verifyApiState"
                      or (s["action"] == "verifyCountChangedBy" and s.get("delta") not in (0, None))
                      for s in verifies) or "reloadAndVerify" in actions
        if not ui_signal:
            score -= 35
            issues.append("submit: a positive submit needs a UI success signal (message, URL, new row)")
        if not backend:
            score -= 35
            issues.append("submit: a positive submit needs backend evidence — verifyRequest with a 2xx/3xx status, "
                          "reloadAndVerify, verifyApiState or verifyCountChangedBy")

    if xss:
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
