"""
admission.py — Phase 10.1 burn-in admission and 10.3 order independence.

Admission: a spec that is new (or healed) in test_suite.json runs `--repeat-each=5` before it joins the regression
suite. Per test: 5/5 passes -> admitted; some passes -> quarantined (reason burn_in_failed, quarantine.yaml);
0/5 -> it fails consistently: not admitted, left for triage (a product defect or a broken test, not flakiness).
At most MAX_SPECS specs per run (oldest first); the rest are `deferred` to the next run.
The spec's `admission` field records the outcome; status `admitted` once every test of it is admitted.

Order independence (nightly): the same tests run three ways — the normal run, one spec file per run in reverse file
order (no browser state shared with another file; app state left in the opposite order), and 4 workers (different
interleaving). A test that passes in one mode and fails in
another is `order_dependent` and quarantined with that reason.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from tools.execution import quarantine as qz

BURN_IN = 5
MAX_SPECS = 50          # specs burned in per run; the rest wait for the next nightly (a fresh suite is all "new")
Runner = Callable[[Dict[str, Any]], Dict[str, Any]]      # a UIExecutionAgent request -> its result


def _ui_runner(project: str, settings: Optional[dict] = None) -> Runner:
    def _run(extra: Dict[str, Any]) -> Dict[str, Any]:
        from agents.test_execution.ui_execution.agent import UIExecutionAgent
        return UIExecutionAgent(settings=settings or {}).execute({"project_name": project, "headless": True, **extra}, {})
    return _run


def _report_statuses(result: Dict[str, Any]) -> Dict[str, List[str]]:
    from tools.triage.service import statuses_from_report
    path = result.get("report_json")
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        rep = json.load(fh)
    return {f"{k[0]} :: {k[1]}": v["statuses"] for k, v in statuses_from_report(rep).items()}


def _suite(project_dir: str) -> dict:
    from contracts.artifacts import load_payload
    return load_payload("test_suite", os.path.join(project_dir, "test_creation", "test_suite.json"), {}) or {}


def admit(project_dir: str, project: str, runner: Optional[Runner] = None, repeat: int = BURN_IN,
          statuses_new: tuple = ("new", "healed"), max_specs: int = MAX_SPECS) -> Dict[str, Any]:
    from contracts.artifacts import save_artifact
    suite = _suite(project_dir)
    pending = [s for s in suite.get("specs") or [] if s.get("status") in statuses_new and s.get("file")]
    candidates = pending[:max_specs]
    if not candidates:
        return {"admitted": [], "quarantined": [], "failing": [], "specs": 0, "deferred": 0}
    runner = runner or _ui_runner(project)
    out = runner({"spec_files": [s["file"] for s in candidates], "repeat_each": repeat})
    statuses = _report_statuses(out)
    q = qz.load(project_dir)
    admitted, quarantined, failing = [], [], []
    errors = {qz.test_key(r.get("spec_file", ""), r.get("test_title", "")): " ".join(r.get("errors") or [])
              for r in out.get("results") or []}
    for key, sts in statuses.items():
        passes = sum(1 for s in sts if s in ("passed", "expected"))
        if passes == len(sts) and len(sts) >= repeat:
            admitted.append(key)
        elif passes:
            qz.add(q, key, "burn_in_failed", errors.get(key, ""))
            quarantined.append(key)
        else:
            failing.append(key)
    qz.save(project_dir, q)
    now = datetime.now(timezone.utc).isoformat()
    for spec in candidates:
        mine = [k for k in statuses if k.startswith(spec["file"] + " :: ")]
        spec["admission"] = {"at": now, "repeat_each": repeat,
                             "admitted": sum(1 for k in mine if k in admitted),
                             "quarantined": sum(1 for k in mine if k in quarantined),
                             "failing": sum(1 for k in mine if k in failing)}
        if mine and all(k in admitted for k in mine):
            spec["status"] = "admitted"
    save_artifact("test_suite", os.path.join(project_dir, "test_creation", "test_suite.json"), suite)
    return {"specs": len(candidates), "admitted": admitted, "quarantined": quarantined, "failing": failing,
            "deferred": len(pending) - len(candidates)}


def order_check(project_dir: str, project: str, spec_files: List[str], runner: Optional[Runner] = None) -> Dict[str, Any]:
    runner = runner or _ui_runner(project)
    modes: Dict[str, Dict[str, List[str]]] = {}
    modes["normal"] = _report_statuses(runner({"spec_files": spec_files}))
    isolated: Dict[str, List[str]] = {}
    for f in reversed(spec_files):          # one file per run, in reverse order: no state from the files before it
        isolated.update(_report_statuses(runner({"spec_files": [f], "workers": 1})))
    modes["isolated_reverse"] = isolated
    modes["workers4"] = _report_statuses(runner({"spec_files": spec_files, "workers": 4}))

    def verdict(sts: List[str]) -> str:
        if not sts:
            return "missing"
        if all(s in ("passed", "expected") for s in sts):
            return "pass"
        return "flaky" if "flaky" in sts else "fail"
    keys = sorted(set().union(*[set(m) for m in modes.values()]))
    dependent = []
    for k in keys:
        v = {m: verdict(modes[m].get(k, [])) for m in modes}
        seen = {x for x in v.values() if x in ("pass", "fail")}
        if seen == {"pass", "fail"}:
            dependent.append({"test": k, "modes": v})
    q = qz.load(project_dir)
    for d in dependent:
        qz.add(q, d["test"], "order_dependent", f"passes/fails by run mode: {d['modes']}")
    qz.save(project_dir, q)
    return {"tests": len(keys), "order_dependent": dependent}
