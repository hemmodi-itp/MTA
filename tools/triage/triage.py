"""Deterministic failure triage (Phase 6). No LLM here: classifies each failed test from the Playwright JSON
(+ MTA reporter / fixture annotations) and records the evidence behind every verdict.

Order (first match wins):
    flaky          Playwright status "flaky" (failed, then passed on retry)
    known_issue    matches an entry in the project's known_issues.yaml
    environment    infrastructure error text, or a 502/503/504 response
    product_defect a 5xx response, or new console errors, or the error reports an HTTP 4xx/5xx
    test_defect.data     collision / duplicate / missing precondition or fixture
    test_defect.locator  strict-mode violation
    product_defect       element not found and the failure-time identity probe found nothing like it on the page
    test_defect.locator  element not found and the probe found the same element (the locator drifted)
    product_defect       an expect(locator) assertion's element never appeared (no recorded identity to probe)
    test_defect.locator  element not found / timed out waiting for it (an action step)
    product_defect an assertion on an expected value failed while the locators resolved
    product_defect a 4xx response during the test (only when nothing above explains the failure)
    unknown        nothing matched (tools/triage/service.py may re-run it or ask an LLM, with evidence)

Extra evidence (never changes the verdict by itself): run history of the test, and whether the same test passes
in another browser of the same run. Responses a test mocked itself (`(mocked)` in the annotation) are ignored.
"""

import json
import os
import re
from datetime import date
from typing import Any, Dict, Iterator, List, Optional

PRODUCT_DEFECT = "product_defect"
LOCATOR = "test_defect.locator"
DATA = "test_defect.data"
ENVIRONMENT = "environment"
FLAKY = "flaky"
KNOWN_ISSUE = "known_issue"
UNKNOWN = "unknown"
VERDICTS = (PRODUCT_DEFECT, LOCATOR, DATA, ENVIRONMENT, FLAKY, KNOWN_ISSUE, UNKNOWN)

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
_STRICT_RE = re.compile(r"strict mode violation", re.I)
# an expect(locator) assertion (not an action such as locator.click) whose element was never found
_ASSERT_MISSING_RE = re.compile(r"expect\(locator\)\.\w+\(.{0,1500}?(?:element\(s\) not found|waiting for)", re.I | re.S)
_ASSERT_RE = re.compile(r"expect\(|Expected[: ]|toHaveText|toBe\(|toEqual|toContain|toHaveValue|Received[: ]", re.I)
_HTTP_BAD_RE = re.compile(r"(?:status|response|HTTP)\D{0,20}\b([45]\d\d)\b|\b([45]\d\d)\b\s+(?:Internal|Bad|Not Found|Forbidden)", re.I)
_STATUS_IN = re.compile(r"\b([1-5]\d\d)\b")


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


# ── known issues ─────────────────────────────────────────────────────────────

def load_known_issues(project_dir: str) -> List[Dict[str, Any]]:
    """known_issues.yaml at the project root:

        issues:
          - id: KI-12
            test: "checkout total"          # regex on the test title (optional)
            spec: "M04/"                    # substring of the spec path (optional)
            error: "Total: \\$1[0-9]"       # regex on the error (optional)
            ticket: SHOP-381
            expires: 2026-12-31             # optional — an expired entry no longer matches
            note: rounding bug, fix planned
    An entry needs at least one of test / spec / error. Malformed entries are skipped."""
    path = os.path.join(project_dir or "", "known_issues.yaml")
    if not os.path.isfile(path):
        return []
    import yaml
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return []
    out = []
    for e in raw.get("issues") or []:
        if isinstance(e, dict) and any(e.get(k) for k in ("test", "spec", "error")):
            out.append(e)
    return out


def match_known_issue(issues: List[Dict[str, Any]], spec_file: str, title: str, error: str,
                      today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    today = today or date.today()
    for e in issues or []:
        exp = e.get("expires")
        if exp:
            try:
                if (exp if isinstance(exp, date) else date.fromisoformat(str(exp))) < today:
                    continue
            except ValueError:
                continue
        try:
            if e.get("test") and not re.search(str(e["test"]), title or "", re.I):
                continue
            if e.get("error") and not re.search(str(e["error"]), error or "", re.I | re.S):
                continue
        except re.error:
            continue
        if e.get("spec") and str(e["spec"]) not in (spec_file or ""):
            continue
        return e
    return None


# ── classification ───────────────────────────────────────────────────────────

def _net_statuses(annotations: List[dict]) -> List[tuple]:
    """[(status, description)] from network_error / http_error annotations, ignoring responses the test mocked."""
    out = []
    for a in annotations:
        if str(a.get("type", "")) not in ("network_error", "http_error"):
            continue
        desc = str(a.get("description", ""))
        if "(mocked)" in desc:
            continue
        m = _STATUS_IN.findall(desc)
        out.append((int(m[-1]) if m else 0, desc))
    return out


_ANSI = re.compile(r"\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Playwright colours its messages (expect([22m locator ...) — the patterns need the plain text."""
    return _ANSI.sub("", text or "")


def classify(status: str, error: str, annotations: Optional[List[dict]] = None,
             known: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return {"verdict", "evidence": [...]} for one failed/flaky test."""
    annotations = annotations or []
    error = strip_ansi(error)
    if status == "flaky":
        return {"verdict": FLAKY, "evidence": ["Playwright status 'flaky' (failed first attempt, passed on retry)"]}
    if known:
        return {"verdict": KNOWN_ISSUE, "evidence": [
            f"matches known_issues.yaml entry {known.get('id', '?')}"
            + (f" ({known['ticket']})" if known.get("ticket") else "")
            + (f": {known['note']}" if known.get("note") else "")]}

    ev: List[str] = []
    console = [a for a in annotations if str(a.get("type", "")).startswith("console_new_error")]
    net = _net_statuses(annotations)
    m = _HTTP_BAD_RE.search(error or "")
    msg_status = (m.group(1) or m.group(2)) if m else None

    # 1. environment wins: nothing about the app's behaviour can be concluded.
    env_m = _ENV_RE.search(error or "")
    if env_m:
        return {"verdict": ENVIRONMENT, "evidence": [f"error matches infrastructure pattern: {env_m.group(0)!r}"]}
    gateway = [d for code, d in net if code in (502, 503, 504)]
    if gateway:
        return {"verdict": ENVIRONMENT, "evidence": [f"gateway response from infrastructure: {gateway[0]}"]}

    # 2. product evidence: server errors / new console errors observed during the test.
    server = [d for code, d in net if code >= 500]
    if server:
        ev.append(f"unexpected 5xx response(s): {server[:3]}")
    elif msg_status:
        ev.append(f"error message reports HTTP {msg_status}")
    if console:
        ev.append(f"new console error(s): {[a.get('description', '') for a in console][:3]}")
    if ev:
        return {"verdict": PRODUCT_DEFECT, "evidence": ev}

    # 3. test defects — or a missing element, which is the product's when nothing like it is on the page.
    if _DATA_RE.search(error or ""):
        return {"verdict": DATA, "evidence": ["error indicates data collision / missing precondition or fixture"]}
    if _STRICT_RE.search(error or ""):
        return {"verdict": LOCATOR, "evidence": ["strict-mode violation: the locator matches several elements"]}
    if _LOCATOR_RE.search(error or ""):
        probes = [str(a.get("description", "")) for a in annotations if a.get("type") == "locator_probe"]
        if any("no element with this identity" in p for p in probes):
            return {"verdict": PRODUCT_DEFECT, "evidence": [
                f"identity probe: {next(p for p in probes if 'no element with this identity' in p)} — the expected "
                "element is missing, not just its locator"]}
        if any("same identity is on the page" in p for p in probes):
            return {"verdict": LOCATOR, "evidence": [
                f"identity probe: {next(p for p in probes if 'same identity' in p)}"]}
        if _ASSERT_MISSING_RE.search(error or ""):
            return {"verdict": PRODUCT_DEFECT, "evidence": [
                "an assertion's element never appeared, after every earlier step passed — the expected outcome is "
                "missing (no recorded identity to tell a moved element from a missing one)"]}
        return {"verdict": LOCATOR, "evidence": ["locator not found / timed out waiting for element"]}

    # 4. assertion on an expected value, locators resolved (no locator error above) → product.
    if _ASSERT_RE.search(error or ""):
        return {"verdict": PRODUCT_DEFECT, "evidence": ["assertion on expected value failed; no locator-resolution error"]}
    client = [d for code, d in net if 400 <= code < 500]
    if client:
        return {"verdict": PRODUCT_DEFECT, "evidence": [f"unexpected 4xx response(s): {client[:3]}"]}
    return {"verdict": UNKNOWN, "evidence": ["no deterministic signal matched"]}


# ── extra signals ────────────────────────────────────────────────────────────

def _statuses(data: dict) -> Dict[tuple, List[str]]:
    """{(spec_key, title): [status per project/repeat]} for one Playwright JSON report."""
    out: Dict[tuple, List[str]] = {}
    for suite in _iter_suites(data.get("suites", [])):
        for spec in suite.get("specs", []):
            key = (_spec_key(spec.get("file", "")), spec.get("title", ""))
            for t in spec.get("tests", []):
                out.setdefault(key, []).append(t.get("status", ""))
    return out


def history(report_json: str, limit: int = 5) -> Dict[tuple, List[str]]:
    """Statuses of each test in the `limit` reports before this one in the same folder (oldest first)."""
    folder = os.path.dirname(report_json)
    name = os.path.basename(report_json)
    try:
        prior = sorted(f for f in os.listdir(folder) if f.endswith("_results.json") and f < name)[-limit:]
    except OSError:
        return {}
    out: Dict[tuple, List[str]] = {}
    for f in prior:
        try:
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                for key, sts in _statuses(json.load(fh)).items():
                    out.setdefault(key, []).append("passed" if all(s in ("passed", "expected") for s in sts)
                                                   else "failed")
        except (OSError, ValueError):
            continue
    return out


def _history_note(runs: List[str]) -> Optional[str]:
    if not runs:
        return None
    flips = sum(1 for a, b in zip(runs, runs[1:]) if a != b)
    note = f"history: {runs.count('passed')}/{len(runs)} previous run(s) passed"
    if flips >= 2:
        note += f", status flipped {flips}x — intermittent"
    elif runs[-1] == "passed":
        note += " (passed last time — a new failure)"
    return note


# ── report ───────────────────────────────────────────────────────────────────

def triage_report(report_json: str, project_dir: str = "", with_history: bool = True) -> Dict[str, Any]:
    """Classify every non-passing test in a Playwright JSON report."""
    with open(report_json, encoding="utf-8") as f:
        data = json.load(f)
    issues = load_known_issues(project_dir) if project_dir else []
    past = history(report_json) if with_history else {}
    per_test = _statuses(data)
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
                    err = strip_ansi(e.get("message", "") or e.get("value", "")) or err
                    if err:
                        break
                key = (_spec_key(spec.get("file", "")), spec.get("title", ""))
                known = match_known_issue(issues, key[0], key[1], err)
                v = classify(status, err, _annotations(results, test), known)
                others = per_test.get(key, [])
                if len(others) > 1 and any(s in ("passed", "expected") for s in others):
                    v["evidence"].append(f"cross-browser: passes in another browser of this run "
                                         f"({test.get('projectName') or 'this project'} failed)")
                note = _history_note(past.get(key, []))
                if note:
                    v["evidence"].append(note)
                items.append({"spec_file": key[0], "test_name": key[1], "project": test.get("projectName", ""),
                              "status": status, "error": err[:500], **v})
    return {"report": os.path.basename(report_json), "counts": count(items), "tests": items}


def count(items: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for it in items:
        counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
    return counts


def write_triage(report_json: str, out_path: str, project_dir: str = "") -> Dict[str, Any]:
    result = triage_report(report_json, project_dir)
    save(result, out_path)
    return result


def save(result: Dict[str, Any], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
