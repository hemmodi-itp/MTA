"""
quarantine.py — Phase 10.2: flaky-test management.

<project>/quarantine.yaml
    release_after: 5            # stable runs in a row before a quarantined test is released (default 5)
    tests:
      - test: "M03/test_x.spec.ts :: create a product @smoke"     # spec key :: title
        first_seen: 2026-10-15
        reason: flaky | burn_in_failed | order_dependent | manual
        failure_signature: "Timeout 5000ms exceeded waiting for getByTestId('save')"
        owner: qa-team          # optional
        stable_runs: 2
    released:                   # history: what left the quarantine and when
      - {test: ..., released: 2026-10-20, after_runs: 5}

A quarantined test still RUNS (its result is reported) but does not GATE: the quality gates and pass rates ignore it.
`record_run` (after every run) counts its passes; `release_after` passes in a row release it, a failure resets the
count. A test that fails twice as flaky outside quarantine is added automatically.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

import yaml

FILE = "quarantine.yaml"
DEFAULT_RELEASE_AFTER = 5
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def test_key(spec_file: str, title: str) -> str:
    from tools.triage.triage import _spec_key
    return f"{_spec_key(spec_file or '')} :: {(title or '').strip()}"


def signature(error: str) -> str:
    """A short, run-independent signature: first error line, numbers and quoted values blurred."""
    line = next((ln.strip() for ln in _ANSI.sub("", error or "").splitlines() if ln.strip()), "")
    line = re.sub(r"\d+", "N", line)
    return line[:160]


def load(project_dir: str) -> Dict[str, Any]:
    path = os.path.join(project_dir, FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    raw.setdefault("release_after", DEFAULT_RELEASE_AFTER)
    raw["tests"] = [t for t in raw.get("tests") or [] if isinstance(t, dict) and t.get("test")]
    raw["released"] = list(raw.get("released") or [])
    return raw


def save(project_dir: str, q: Dict[str, Any]) -> None:
    with open(os.path.join(project_dir, FILE), "w", encoding="utf-8") as fh:
        yaml.safe_dump(q, fh, sort_keys=False, allow_unicode=True)


def keys(q: Dict[str, Any]) -> set:
    return {t["test"] for t in q.get("tests") or []}


def add(q: Dict[str, Any], key: str, reason: str, error: str = "", owner: Optional[str] = None,
        today: Optional[date] = None) -> bool:
    """False when the test is already quarantined."""
    if key in keys(q):
        return False
    entry = {"test": key, "first_seen": (today or date.today()).isoformat(), "reason": reason,
             "failure_signature": signature(error), "stable_runs": 0}
    if owner:
        entry["owner"] = owner
    q["tests"].append(entry)
    return True


def _status(r: dict) -> str:
    s = str(r.get("pw_status") or r.get("status") or "").lower()
    return {"expected": "passed", "success": "passed", "unexpected": "failed", "failure": "failed"}.get(s, s)


def record_run(project_dir: str, results: Iterable[dict], today: Optional[date] = None,
               flaky_history: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """After a run: count stable passes of quarantined tests, release them after `release_after`, reset on failure;
    quarantine a test that is flaky again (flaky_history: key -> earlier flaky count). Returns what changed."""
    q = load(project_dir)
    by_key = {test_key(r.get("spec_file", ""), r.get("test_title", "")): r for r in results}
    released, reset, added = [], [], []
    keep = []
    for t in q["tests"]:
        r = by_key.get(t["test"])
        if r is None:
            keep.append(t)
            continue
        st = _status(r)
        if st == "passed":
            t["stable_runs"] = int(t.get("stable_runs") or 0) + 1
        elif st in ("failed", "flaky"):
            if t.get("stable_runs"):
                reset.append(t["test"])
            t["stable_runs"] = 0
        if t["stable_runs"] >= int(q["release_after"]):
            released.append(t["test"])
            q["released"].append({"test": t["test"], "released": (today or date.today()).isoformat(),
                                  "after_runs": t["stable_runs"]})
        else:
            keep.append(t)
    q["tests"] = keep
    for key, r in by_key.items():
        if _status(r) == "flaky" and key not in keys(q) and (flaky_history or {}).get(key, 0) >= 1:
            add(q, key, "flaky", " ".join(r.get("errors") or []), today=today)
            added.append(key)
    if added or os.path.isfile(os.path.join(project_dir, FILE)):     # no file is created for a project that never needed one
        save(project_dir, q)
    return {"released": released, "reset": reset, "added": added, "quarantined": sorted(keys(q))}


def split_results(results: List[dict], q: Dict[str, Any]) -> tuple:
    """(gating, quarantined): quarantined tests are reported but do not count for gates or pass rates."""
    qk = keys(q)
    gating, quarantined = [], []
    for r in results:
        (quarantined if test_key(r.get("spec_file", ""), r.get("test_title", "")) in qk else gating).append(r)
    return gating, quarantined


def flaky_counts(reports_json_dir: str, limit: int = 10) -> Dict[str, int]:
    """How often each test was flaky in the last `limit` Playwright JSON reports."""
    import json
    from tools.triage.service import statuses_from_report
    out: Dict[str, int] = {}
    try:
        files = sorted(f for f in os.listdir(reports_json_dir) if f.endswith("_results.json"))[-limit:]
    except OSError:
        return out
    for f in files:
        try:
            with open(os.path.join(reports_json_dir, f), encoding="utf-8") as fh:
                rep = json.load(fh)
        except (OSError, ValueError):
            continue
        for (spec, title), v in statuses_from_report(rep).items():
            if "flaky" in v["statuses"]:
                k = f"{spec} :: {title}"
                out[k] = out.get(k, 0) + 1
    return out
