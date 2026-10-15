"""
regression_gate.py — Phase 12.5: benchmark metric regression gates (the nightly benchmark job runs it last).

    python -m tools.benchmark.regression_gate [--results benchmarks/results] [--baselines benchmarks/baselines.json]
                                              [--require KIND,...] [--update]

For every benchmark kind it takes the LATEST result file (date prefix, then modification time) and compares its
metrics with benchmarks/baselines.json:
    higher   (detection rates, coverage, mutation score, ...)  fails when the value DROPS below the baseline
    lower    (false-failure rates)                              fails when the value RISES above the baseline
    floor    (heal precision)                                   fails below an absolute minimum (95%)
Exit 1 names every failed metric; exit 0 otherwise. A metric the run did not measure (None) is reported, not failed.
A kind with no result file is reported; `--require` makes it a failure (the nightly job requires what it ran).
`--update` writes the latest values as the new baselines (after an intended change — review the diff).

Kinds (the result file each benchmark writes):
    e2e              tools.benchmark.run (any label; recognised by metrics.seeded_bug_detection)
    phase6_healing   tools.benchmark.healing_bench
    phase7_nfr       tools.benchmark.nfr_bench
    phase8_whitebox  tools.benchmark.whitebox_bench
    phase10_ci       tools.benchmark.ci_bench
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks" / "results"
BASELINES = ROOT / "benchmarks" / "baselines.json"
HEAL_PRECISION_FLOOR = 0.95
_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})_(?P<app>[a-z0-9]+(?:_[a-z0-9]+)*?)_(?P<label>phase\d+_[a-z]+)\.json$")


def _get(d: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _ratio(num: Any, den: Any) -> Optional[float]:
    return round(num / den, 4) if isinstance(num, (int, float)) and isinstance(den, (int, float)) and den else (
        0.0 if den == 0 and num == 0 else None)


# metric name -> (direction, extractor); direction: higher | lower | floor
Metric = Tuple[str, Callable[[dict], Optional[float]]]
KINDS: Dict[str, Dict[str, Metric]] = {
    "e2e": {
        "detection_rate": ("higher", lambda d: _get(d, "metrics.seeded_bug_detection.rate")),
        "false_failure_rate": ("lower", lambda d: _get(d, "metrics.false_failure.rate")),
        "flaky_rate": ("lower", lambda d: _get(d, "metrics.flaky.rate")),
        "heal_precision": ("floor", lambda d: _get(d, "metrics.heal_precision.precision")),
        "ac_extraction_recall": ("higher", lambda d: _get(d, "metrics.ac_extraction_recall")),
    },
    "phase6_healing": {
        "detection_rate": ("higher", lambda d: _ratio(_get(d, "summary.bugs_detected"), _get(d, "summary.bugs"))),
        "false_failure_rate": ("lower", lambda d: _ratio(_get(d, "clean.failed"),
                                                         (_get(d, "clean.passed") or 0) + (_get(d, "clean.failed") or 0))),
        "heal_precision": ("floor", lambda d: _ratio((_get(d, "summary.healed") or 0) - (_get(d, "summary.wrong_element_heals") or 0),
                                                     _get(d, "summary.healed")) if _get(d, "summary.healed") else None),
        "heal_success_pct": ("higher", lambda d: _get(d, "summary.heal_success_pct")),
    },
    "phase7_nfr": {
        "detection_rate": ("higher", lambda d: _ratio(_get(d, "summary.detected"), _get(d, "summary.targets"))),
        "false_failure_rate": ("lower", lambda d: _ratio(_get(d, "summary.clean_failures"), _get(d, "clean.tests"))),
    },
    "phase8_whitebox": {
        "detection_rate": ("higher", lambda d: _ratio(_get(d, "summary.bugs_caught"), _get(d, "summary.bugs"))),
        "false_failure_rate": ("lower", lambda d: _ratio(_get(d, "api_clean.failed"), _get(d, "api_clean.tests"))),
        "endpoint_coverage_pct": ("higher", lambda d: _get(d, "api.endpoint_coverage_pct")),
        "mutation_score_pct": ("higher", lambda d: _get(d, "mutation.score_pct")),
    },
    "phase10_ci": {
        "checks_pass_rate": ("higher", lambda d: _ratio(_get(d, "passed"), _get(d, "total"))),
    },
}


def kind_of(path: Path, doc: Optional[dict] = None) -> Optional[str]:
    m = _NAME.match(path.name)
    if m and m.group("label") in KINDS:
        return m.group("label")
    if doc is None:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return "e2e" if isinstance(_get(doc, "metrics.seeded_bug_detection"), dict) else None


def latest(results: Path = RESULTS) -> Dict[str, Path]:
    """kind -> newest result file (date prefix, then mtime)."""
    out: Dict[str, Path] = {}
    for p in sorted(results.glob("*.json"), key=lambda p: (p.name[:10], p.stat().st_mtime)):
        k = kind_of(p)
        if k:
            out[k] = p
    return out


def metrics(kind: str, doc: dict) -> Dict[str, Optional[float]]:
    return {name: (fn(doc)) for name, (_dir, fn) in KINDS[kind].items()}


def compare(kind: str, values: Dict[str, Optional[float]], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for name, (direction, _fn) in KINDS[kind].items():
        v, b = values.get(name), (baseline or {}).get(name)
        row = {"kind": kind, "metric": name, "direction": direction, "value": v, "baseline": b, "ok": True, "note": ""}
        if direction == "floor":
            row["baseline"] = HEAL_PRECISION_FLOOR
        if v is None:
            row["note"] = "not measured in this run"
        elif direction == "floor":
            row["ok"] = v >= HEAL_PRECISION_FLOOR
        elif b is None:
            row["note"] = "no baseline yet"
        elif direction == "higher":
            row["ok"] = v >= b
        else:
            row["ok"] = v <= b
        rows.append(row)
    return rows


def gate(results: Path = RESULTS, baselines_path: Path = BASELINES, require: Tuple[str, ...] = ()) -> Tuple[int, List[dict], List[str]]:
    base = json.loads(baselines_path.read_text(encoding="utf-8")) if baselines_path.is_file() else {}
    files = latest(results)
    rows: List[dict] = []
    notes: List[str] = []
    for kind in KINDS:
        if kind not in files:
            notes.append(f"{kind}: no result file" + (" - REQUIRED" if kind in require else ""))
            continue
        doc = json.loads(files[kind].read_text(encoding="utf-8"))
        for r in compare(kind, metrics(kind, doc), (base.get(kind) or {}).get("metrics") or {}):
            r["file"] = files[kind].name
            rows.append(r)
    failed = [r for r in rows if not r["ok"]] or [n for n in notes if n.endswith("REQUIRED")]
    return (1 if failed else 0), rows, notes


def update(results: Path = RESULTS, baselines_path: Path = BASELINES) -> dict:
    base = json.loads(baselines_path.read_text(encoding="utf-8")) if baselines_path.is_file() else {}
    for kind, path in latest(results).items():
        values = metrics(kind, json.loads(path.read_text(encoding="utf-8")))
        base[kind] = {"from": path.name, "metrics": {k: v for k, v in values.items()
                                                     if v is not None and KINDS[kind][k][0] != "floor"}}
    baselines_path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
    return base


def _fmt(v: Any) -> str:
    return "n/a" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--results", default=str(RESULTS))
    ap.add_argument("--baselines", default=str(BASELINES))
    ap.add_argument("--require", default="", help="comma list of kinds that must have a result file")
    ap.add_argument("--update", action="store_true", help="write the latest values as the new baselines")
    args = ap.parse_args(argv)
    results, baselines = Path(args.results), Path(args.baselines)
    if args.update:
        base = update(results, baselines)
        print(f"baselines updated from: {', '.join(v['from'] for v in base.values())}")
        return 0
    require = tuple(k.strip() for k in args.require.split(",") if k.strip())
    unknown = sorted(set(require) - set(KINDS))
    if unknown:
        print(f"unknown kind(s) {unknown}; known: {sorted(KINDS)}")
        return 2
    code, rows, notes = gate(results, baselines, require)
    for r in rows:
        mark = "ok" if r["ok"] else "FAIL"
        rule = {"higher": "must not drop below", "lower": "must not rise above", "floor": "must be at least"}[r["direction"]]
        print(f"[{mark}] {r['kind']}.{r['metric']} = {_fmt(r['value'])} ({rule} {_fmt(r['baseline'])})"
              f"{' - ' + r['note'] if r['note'] else ''}  [{r['file']}]")
    for n in notes:
        print(f"[note] {n}")
    failed = [f"{r['kind']}.{r['metric']}" for r in rows if not r["ok"]]
    if code:
        print("REGRESSION: " + (", ".join(failed) if failed else "a required benchmark did not produce a result"))
    return code


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
