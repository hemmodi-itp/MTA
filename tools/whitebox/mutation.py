"""
mutation.py — Phase 8.5 / 12.6: mutation testing with a built-in runner (no mutmut / Stryker needed). Scheduled, not
per run, and only for code the team owns.

One mutant = one small change in one of the selected functions:
    comparison   <  <=   >  >=   ==  !=   in  not in   is  is not      (each swapped with its neighbour)
    condition    `if not x` -> `if x`,  `if x` -> `if not x`
    boolean      and <-> or,  True <-> False
    number       an int constant n -> n + 1
The file is rewritten, the test command runs, the original is restored (always — also a backup left by an
interrupted run is restored first). A mutant is KILLED when the tests fail, SURVIVED when they pass; the mutation
score = killed / (killed + survived) is the strongest measure of how many faults the tests catch.

    python -m tools.whitebox.mutation --file benchmarks/apps/buggy_shop/app.py \
        --functions validate_product,parse_quantity --cmd "python -m pytest tests/x -q" [--max 30] [--timeout 600]
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
         ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
BACKUP_SUFFIX = ".mta-mutation-backup"


@dataclass
class Mutant:
    index: int
    function: str
    line: int
    description: str
    status: str = "pending"          # killed | survived | timeout | error
    seconds: float = 0.0


def _sites(tree: ast.AST, functions: Sequence[str]) -> List[tuple]:
    """[(node_path, kind, function, line, description)] — every mutable spot inside the selected functions."""
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or (functions and fn.name not in functions):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare):
                for i, op in enumerate(node.ops):
                    if type(op) in _SWAP:
                        out.append((node, ("cmp", i), fn.name, node.lineno,
                                    f"{type(op).__name__} -> {_SWAP[type(op)].__name__}"))
            elif isinstance(node, (ast.If, ast.While)):
                neg = isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not)
                out.append((node, ("cond",), fn.name, node.lineno, "drop `not`" if neg else "negate condition"))
            elif isinstance(node, ast.BoolOp):
                out.append((node, ("boolop",), fn.name, node.lineno,
                            f"{type(node.op).__name__} -> {'Or' if isinstance(node.op, ast.And) else 'And'}"))
            elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
                out.append((node, ("bool",), fn.name, node.lineno, f"{node.value} -> {not node.value}"))
            elif isinstance(node, ast.Constant) and type(node.value) is int:
                out.append((node, ("int",), fn.name, node.lineno, f"{node.value} -> {node.value + 1}"))
    return out


def mutants(source: str, functions: Sequence[str] = ()) -> List[tuple]:
    """[(Mutant, mutated_source)] in source order."""
    tree = ast.parse(source)
    sites = _sites(tree, functions)
    out = []
    for i in range(len(sites)):
        t2 = copy.deepcopy(tree)
        node, kind, fn, line, desc = _sites(t2, functions)[i]
        if kind[0] == "cmp":
            node.ops[kind[1]] = _SWAP[type(node.ops[kind[1]])]()
        elif kind[0] == "cond":
            neg = isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not)
            node.test = node.test.operand if neg else ast.UnaryOp(op=ast.Not(), operand=node.test)
        elif kind[0] == "boolop":
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        elif kind[0] == "bool":
            node.value = not node.value
        elif kind[0] == "int":
            node.value = node.value + 1
        ast.fix_missing_locations(t2)
        out.append((Mutant(i, fn, line, desc), ast.unparse(t2)))
    return out


def restore_leftover(path: Path) -> bool:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if backup.exists():
        shutil.copyfile(backup, path)
        backup.unlink()
        return True
    return False


def run(file: str, functions: Sequence[str], test: Callable[[], bool], max_mutants: Optional[int] = None,
        log: Callable[[str], None] = print) -> dict:
    """test() -> True when the suite PASSES. Returns {score, killed, survived, mutants: [...]}."""
    path = Path(file)
    restore_leftover(path)
    original = path.read_text(encoding="utf-8")
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    shutil.copyfile(path, backup)
    results: List[Mutant] = []
    try:
        todo = mutants(original, functions)
        if max_mutants:
            step = max(1, len(todo) // max_mutants)
            todo = todo[::step][:max_mutants]            # spread over the functions, not just the first lines
        for m, src in todo:
            path.write_text(src, encoding="utf-8")
            t0 = time.monotonic()
            try:
                passed = test()
                m.status = "survived" if passed else "killed"
            except subprocess.TimeoutExpired:
                m.status = "timeout"                     # a hang counts as detected, reported separately
            except Exception as exc:                     # noqa: BLE001 — the harness, not the mutant, failed
                m.status = f"error: {type(exc).__name__}"
            finally:
                path.write_text(original, encoding="utf-8")
            m.seconds = round(time.monotonic() - t0, 1)
            results.append(m)
            log(f"mutant {m.index} {m.function}:{m.line} {m.description} -> {m.status}")
    finally:
        path.write_text(original, encoding="utf-8")
        backup.unlink(missing_ok=True)
    killed = sum(1 for m in results if m.status in ("killed", "timeout"))
    survived = [m for m in results if m.status == "survived"]
    scored = killed + len(survived)
    return {"file": file, "functions": list(functions), "mutants": len(results), "killed": killed,
            "survived": len(survived), "score_pct": round(100.0 * killed / scored, 1) if scored else None,
            "survivors": [asdict(m) for m in survived], "results": [asdict(m) for m in results]}


def command_test(cmd: str, timeout: int = 600) -> Callable[[], bool]:
    def _run() -> bool:
        proc = subprocess.run(cmd, shell=True, timeout=timeout, capture_output=True)
        return proc.returncode == 0
    return _run


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", required=True)
    ap.add_argument("--functions", default="")
    ap.add_argument("--cmd", required=True, help="test command; exit code 0 = the suite passed")
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", default="")
    args = ap.parse_args(list(argv) if argv is not None else None)
    res = run(args.file, [f for f in args.functions.split(",") if f], command_test(args.cmd, args.timeout), args.max)
    text = json.dumps(res, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("mutants", "killed", "survived", "score_pct")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
