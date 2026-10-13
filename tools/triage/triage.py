"""Deterministic failure triage (Phase 6-lean). No LLM: classifies each failed test from the
Playwright JSON (+ MTA reporter annotations) and records the evidence behind every verdict."""

import json
import os
import re
from typing import Any, Dict, Iterator, List, Optional

PRODUCT_DEFECT = "product_defect"
LOCATOR = "test_defect.locator"
DATA = "test_defect.data"
ENVIRONMENT = "environment"
FLAKY = "flaky"
UNKNOWN = "unknown"

_ENV_RE = re.compile(
    r"ERR_CONNECTION_REFUSED|ERR_NAME_NOT_RESOLVED|ERR_CERT|ECONNREFUSED|ENOTFOUND|net::ERR_|"
    r"\b(?:502|503|504)\b.{0,40}(?:gateway|unavailable|timeout)|(?:gateway|unavailable).{0,40}\b(?:502|503|504)\b|"
    r"storageState|session expired|auth(?:entication)? (?:state )?expired|redirected to /?login", re.I)
_LOCATOR_RE = re.compile(
    r"strict mode violation|waiting for (?:getBy|locator)|element\(s\) not found|locator resolved to 0|"
    r"\[locator_key=[^\]]*\].{0,120}(?:not found|timeout)|Timeout \d+ms exceeded.{0,80}waiting for", re.I | re.S)
_DATA_RE = re.compile(
    r"already exists|duplicate|unique constraint|conflict|precondition|no such (?:user|record)|"
    r"Upload fixture not found|ENOENT", re.I)
_ASSERT_RE = re.compile(r"expect\(|Expected[: ]|toHaveText|toBe\(|toEqual|toContain|toHaveValue|Received[: ]", re.I)
_HTTP_BAD_RE = re.compile(r"(?:status|response|HTTP)\D{0,20}\b([45]\d\d)\b|\b([45]\d\d)\b\s+(?:Internal|Bad|Not Found|Forbidden)", re.I)


def _iter_suites(suites: list) -> Iterator[dict]:
    for s in suites:
        yield s
        yield from _iter_suites(s.get("suites", []))


def _spec_key(path: str) -> str:
    norm = (path or "").replace("\\", "/")
    marker = "test_creation/test_scripts/"
    i = norm.find(marker)
    return norm[i + len(marker):] if i >= 0 else os.path.basename(norm)


def _annotations(results: List[dict], test: dict) -> List[dict]:
    out = list(test.get("annotations") or [])
    for r in results:
        out.extend(r.get("annotations") or [])
    return out


def classify(status: str, error: str, annotations: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Return {"verdict", "evidence": [...]} for one failed/flaky test."""
    annotations = annotations or []
    if status == "flaky":
        return {"verdict": FLAKY, "evidence": ["Playwright status 'flaky' (failed first attempt, passed on retry)"]}

    ev: List[str] = []
    console = [a for a in annotations if str(a.get("type", "")).startswith("console_new_error")]
    net = [a for a in annotations if str(a.get("type", "")) in ("network_error", "http_error")]
    net_bad = [a.get("description", "") for a in net]
    m = _HTTP_BAD_RE.search(error or "")
    msg_status = (m.group(1) or m.group(2)) if m else None

    # 1. environment wins: nothing about the app's behaviour can be concluded.
    env_m = _ENV_RE.search(error or "")
    if env_m:
        return {"verdict": ENVIRONMENT, "evidence": [f"error matches infrastructure pattern: {env_m.group(0)!r}"]}
    gateway = [d for d in net_bad if re.search(r"\b50[234]\b", d)]
    if gateway:
        return {"verdict": ENVIRONMENT, "evidence": [f"gateway response from infrastructure: {gateway[0]}"]}

    # 2. product evidence: server errors / new console errors observed during the test.
    if net_bad:
        ev.append(f"unexpected 4xx/5xx response(s): {net_bad[:3]}")
    elif msg_status:
        ev.append(f"error message reports HTTP {msg_status}")
    if console:
        ev.append(f"new console error(s): {[a.get('description', '') for a in console][:3]}")
    if ev:
        return {"verdict": PRODUCT_DEFECT, "evidence": ev}

    # 3. test defects.
    if _DATA_RE.search(error or ""):
        return {"verdict": DATA, "evidence": ["error indicates data collision / missing precondition or fixture"]}
    if _LOCATOR_RE.search(error or ""):
        return {"verdict": LOCATOR, "evidence": ["locator not found / strict-mode violation / timed out waiting for element"]}

    # 4. assertion on an expected value, locators resolved (no locator error above) → product.
    if _ASSERT_RE.search(error or ""):
        return {"verdict": PRODUCT_DEFECT, "evidence": ["assertion on expected value failed; no locator-resolution error"]}
    return {"verdict": UNKNOWN, "evidence": ["no deterministic signal matched"]}


def triage_report(report_json: str) -> Dict[str, Any]:
    """Classify every non-passing test in a Playwright JSON report."""
    with open(report_json, encoding="utf-8") as f:
        data = json.load(f)
    items: List[dict] = []
    for suite in _iter_suites(data.get("suites", [])):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                status = test.get("status", "")
                if status in ("passed", "expected", "skipped"):
                    continue
                results = test.get("results", [])
                err = ""
                for r in results:
                    e = r.get("error") or {}
                    err = e.get("message", "") or e.get("value", "") or err
                    if err:
                        break
                v = classify(status, err, _annotations(results, test))
                items.append({"spec_file": _spec_key(spec.get("file", "")), "test_name": spec.get("title", ""),
                              "status": status, "error": err[:500], **v})
    counts: Dict[str, int] = {}
    for it in items:
        counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
    return {"report": os.path.basename(report_json), "counts": counts, "tests": items}


def write_triage(report_json: str, out_path: str) -> Dict[str, Any]:
    result = triage_report(report_json)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result
