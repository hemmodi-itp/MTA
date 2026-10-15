"""
mutate_mta.py — Phase 12.6: periodic mutation testing of MTA itself (the built-in runner of tools/whitebox/mutation.py;
mutmut does not run on Windows).

    python -m tools.selftest.mutate_mta [--target bva,ep,triage,linter] [--max-mutants 25] [--time-box 30]
                                        [--timeout 300] [--out benchmarks/results/<date>_mta_selftest_mutation]

Each target file is mutated one small change at a time (comparison / condition / boolean / integer constant, spread
over the whole file) and the unit tests that cover it run against every mutant: a mutant the tests do not notice
SURVIVES — a fault the suite would let through. --max-mutants caps each target; --time-box (minutes, all targets) stops
starting new mutants once spent; the rest are reported as not run. The source is restored after every mutant (and a
backup left by an interrupted run is restored first); at the end `git diff` must be empty for every target.
The covering tests run with PYTHONDONTWRITEBYTECODE=1 so a stale .pyc can never stand in for a mutated file.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]

# target -> (source file, the unit tests that cover it)
TARGETS: Dict[str, tuple] = {
    "bva": ("tools/test_design/bva.py",
            ["tests/unit/test_test_design_bva.py", "tests/unit/test_test_design_generators.py",
             "tests/unit/test_test_design_pipeline.py"]),
    "ep": ("tools/test_design/ep.py",
           ["tests/unit/test_test_design_generators.py", "tests/unit/test_test_design_pipeline.py"]),
    "triage": ("tools/triage/triage.py",
               ["tests/unit/test_triage_and_safe_healing.py", "tests/unit/test_phase6_safe_healing.py"]),
    "linter": ("tools/test_creation/assertion_linter.py",
               ["tests/unit/test_assertion_linter.py", "tests/unit/test_phase5_oracles.py"]),
}


def pytest_test(test_files: List[str], timeout: int):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def _run() -> bool:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *test_files],
                              cwd=ROOT, env=env, timeout=timeout, capture_output=True)
        return proc.returncode == 0
    return _run


def git_clean(files: List[str]) -> bool:
    out = subprocess.run(["git", "diff", "--quiet", "--", *files], cwd=ROOT)
    return out.returncode == 0


def run(targets: List[str], max_mutants: int, time_box_min: float, timeout: int, log=print) -> dict:
    from tools.whitebox import mutation
    deadline = time.monotonic() + time_box_min * 60
    files = [TARGETS[t][0] for t in targets]
    if not git_clean(files):
        raise SystemExit(f"refusing to mutate files with uncommitted changes: {files} (commit or stash first)")
    started = time.monotonic()
    out: Dict[str, dict] = {}
    for t in targets:
        src, tests = TARGETS[t]
        if not pytest_test(tests, timeout)():
            raise SystemExit(f"{t}: the covering tests fail on the unmutated source — fix them first: {tests}")
        log(f"== {t}: {src} ({', '.join(Path(x).name for x in tests)})")
        res = mutation.run(str(ROOT / src), [], pytest_test(tests, timeout), max_mutants=max_mutants, log=log,
                           deadline=deadline)
        res["file"], res["tests"] = src, tests
        res.pop("results", None)
        out[t] = res
    killed = sum(r["killed"] for r in out.values())
    survived = sum(r["survived"] for r in out.values())
    return {"date": date.today().isoformat(), "max_mutants": max_mutants, "time_box_min": time_box_min,
            "seconds": round(time.monotonic() - started), "targets": out,
            "total": {"mutants": killed + survived, "killed": killed, "survived": survived,
                      "score_pct": round(100.0 * killed / (killed + survived), 1) if killed + survived else None,
                      "not_run": sum(r.get("not_run", 0) for r in out.values())},
            "restored": git_clean(files)}


def markdown(res: dict) -> str:
    lines = [f"# MTA self mutation testing ({res['date']})", "",
             f"{res['total']['killed']}/{res['total']['mutants']} mutants killed "
             f"(**{res['total']['score_pct']}%**), {res['total']['not_run']} not run (cap {res['max_mutants']} per "
             f"target, time box {res['time_box_min']} min, {res['seconds']} s). Sources restored: "
             f"{'yes (git diff empty)' if res['restored'] else '**NO**'}.", "",
             "| Target | File | Mutants | Killed | Survived | Score |", "|---|---|---|---|---|---|"]
    for t, r in res["targets"].items():
        lines.append(f"| {t} | `{r['file']}` | {r['mutants']} | {r['killed']} | {r['survived']} | {r['score_pct']}% |")
    lines += ["", "## Survivors (faults the unit tests let through)", ""]
    for t, r in res["targets"].items():
        for m in r["survivors"]:
            lines.append(f"- {t} `{r['file']}:{m['line']}` in `{m['function']}`: {m['description']}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("--target", default=",".join(TARGETS), help=f"comma list of {sorted(TARGETS)}")
    ap.add_argument("--max-mutants", type=int, default=25, help="per target")
    ap.add_argument("--time-box", type=float, default=30.0, help="minutes for all targets")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per test run (a hang counts as killed)")
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / f"{date.today().isoformat()}_mta_selftest_mutation"))
    args = ap.parse_args(argv)
    targets = [t.strip() for t in args.target.split(",") if t.strip()]
    unknown = sorted(set(targets) - set(TARGETS))
    if unknown:
        print(f"unknown target(s) {unknown}; known: {sorted(TARGETS)}")
        return 2
    os.chdir(ROOT)
    res = run(targets, args.max_mutants, args.time_box, args.timeout)
    Path(args.out + ".json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    Path(args.out + ".md").write_text(markdown(res), encoding="utf-8")
    print(markdown(res))
    return 0 if res["restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
