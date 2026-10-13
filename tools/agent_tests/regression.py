"""
regression.py — per-dimension scores per agent version, compared with the previous run (Phase 9.5, design §14 S7).

    entry = history_entry(result, dataset_version=3)
    previous = last_entry(path)
    report = compare(entry, previous, max_drop_points=5.0)    # {"ok": False, "regressions": [...], ...}
    append(path, entry)

History is an append-only JSONL file per agent (default .aqp_artifacts/agent_quality/<agent>.jsonl — outside the
per-run artifact folders, so pruning runs never loses it). A pass-rate drop of more than `max_drop_points`
percentage points in any dimension is a regression and a gate failure; a dimension that was passing its gate and no
longer is, is one too.
"""

import json
import os
from typing import Any, Dict, List, Optional

from tools.agent_tests.runner import pass_rates

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def history_path(agent: str, directory: Optional[str] = None) -> str:
    base = directory or os.environ.get("AQP_AGENT_QUALITY_DIR") or os.path.join(
        os.environ.get("AQP_ARTIFACT_DIR") or os.path.join(REPO_ROOT, ".aqp_artifacts"), "agent_quality")
    return os.path.join(base, f"{agent}.jsonl")


def history_entry(result: Dict[str, Any], dataset_version: Optional[int] = None, date: Optional[str] = None
                  ) -> Dict[str, Any]:
    rates = pass_rates(result)
    return {
        "run_id": result["run_id"], "agent": result["agent"], "agent_version": result.get("agent_version"),
        "dataset_version": dataset_version, "date": date,
        "dimensions": {d: {"pass_rate": rates.get(d), "verdict": v["verdict"]}
                       for d, v in result["dimensions"].items()},
    }


def read(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a torn line never blocks the comparison
    return out


def last_entry(path: str, exclude_run: Optional[str] = None) -> Optional[Dict[str, Any]]:
    entries = [e for e in read(path) if e.get("run_id") != exclude_run]
    return entries[-1] if entries else None


def append(path: str, entry: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")


def compare(current: Dict[str, Any], previous: Optional[Dict[str, Any]], max_drop_points: float = 5.0
            ) -> Dict[str, Any]:
    if previous is None:
        return {"ok": True, "baseline": True, "previous": None, "regressions": [], "dimensions": {},
                "note": "first recorded run of this agent: nothing to compare with"}
    dims: Dict[str, Any] = {}
    regressions: List[Dict[str, Any]] = []
    for dim, cur in current["dimensions"].items():
        prev = (previous.get("dimensions") or {}).get(dim)
        if not prev:
            dims[dim] = {"status": "new"}
            continue
        a, b = prev.get("pass_rate"), cur.get("pass_rate")
        delta = None if a is None or b is None else round((b - a) * 100, 2)
        status = "ok"
        if delta is not None and delta < -max_drop_points:
            status = "regression"
        elif prev.get("verdict") == "pass" and cur.get("verdict") == "fail":
            status = "regression"
        dims[dim] = {"previous": a, "current": b, "delta_points": delta, "previous_verdict": prev.get("verdict"),
                     "current_verdict": cur.get("verdict"), "status": status}
        if status == "regression":
            regressions.append({"dimension": dim, **dims[dim]})
    return {"ok": not regressions, "baseline": False, "max_drop_points": max_drop_points,
            "previous": {k: previous.get(k) for k in ("run_id", "agent_version", "dataset_version", "date")},
            "regressions": regressions, "dimensions": dims}
