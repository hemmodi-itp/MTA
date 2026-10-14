"""
coverage_gap.py — Phase 8.3: coverage report and the gap loop.

    report(data_file, code_rules)  statement % / branch % per file and overall, uncovered critical functions
    gaps(report, code_rules)       uncovered lines -> the function they are in -> the routes that reach that function
                                   (handler, or a helper the handler calls — code_rules' call graph)
    gap_round(project_dir, ...)    API tests for exactly the gap routes (test_scripts/api/gap_*.spec.ts)

"Critical" functions: route handlers and the functions rules come from (validation, access checks).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]


def _rel(path: str, root: Path = ROOT) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def report(data_file: str, code: Optional[dict] = None, root: Path = ROOT) -> Dict[str, Any]:
    import coverage
    cov = coverage.Coverage(data_file=data_file)
    cov.load()
    out_json = os.path.join(tempfile.mkdtemp(), "cov.json")
    cov.json_report(outfile=out_json, show_contexts=False)
    data = json.loads(Path(out_json).read_text(encoding="utf-8"))
    files = {}
    for path, f in data.get("files", {}).items():
        s = f.get("summary") or {}
        files[_rel(path, root)] = {
            "statements": s.get("num_statements", 0), "covered": s.get("covered_lines", 0),
            "branches": s.get("num_branches", 0), "covered_branches": s.get("covered_branches", 0),
            "missing_lines": f.get("missing_lines") or [], "missing_branches": f.get("missing_branches") or [],
        }
    tot = data.get("totals") or {}
    pct = lambda a, b: round(100.0 * a / b, 1) if b else None   # noqa: E731
    critical = _critical(code or {})
    uncovered_critical = []
    for key, fn in (code or {}).get("functions", {}).items():
        if key.split("::")[-1] not in critical:
            continue
        f = files.get(fn["file"])
        if f is None:
            continue
        missing = [ln for ln in f["missing_lines"] if fn["start"] <= ln <= fn["end"]]
        if missing:
            uncovered_critical.append({"function": fn["name"], "file": fn["file"], "missing_lines": missing})
    return {"statement_pct": pct(tot.get("covered_lines", 0), tot.get("num_statements", 0)),
            "branch_pct": pct(tot.get("covered_branches", 0), tot.get("num_branches", 0)),
            "statements": tot.get("num_statements", 0), "branches": tot.get("num_branches", 0),
            "covered_branches": tot.get("covered_branches", 0), "files": files,
            "uncovered_critical": sorted(uncovered_critical, key=lambda x: (-len(x["missing_lines"]), x["function"]))}


def _critical(code: dict) -> set:
    names = {r.get("handler") for r in code.get("routes") or [] if r.get("handler")}
    names |= {r.get("function") for r in code.get("rules") or []}
    names |= {c for r in code.get("routes") or [] for c in r.get("access_checks") or []}
    return {n for n in names if n}


def _reach(code: dict, start: str) -> set:
    seen, todo = set(), [start]
    while todo:
        cur = todo.pop()
        for nxt in code.get("calls", {}).get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def gaps(rep: Dict[str, Any], code: dict) -> List[Dict[str, Any]]:
    """Each function with uncovered lines, and the routes (METHOD template) that can execute those lines."""
    routes_by_fn: Dict[str, set] = {}
    for r in code.get("routes") or []:
        if not r.get("handler") or not r.get("citation"):
            continue
        file = r["citation"].rsplit(":", 1)[0]
        handler_key = f"{file}::{r['handler']}"
        for fn in {handler_key} | _reach(code, handler_key):
            routes_by_fn.setdefault(fn, set()).add(f"{r['method']} {r['path_template']}")
    out = []
    for key, fn in (code.get("functions") or {}).items():
        f = rep["files"].get(fn["file"])
        if not f:
            continue
        missing = [ln for ln in f["missing_lines"] if fn["start"] <= ln <= fn["end"]]
        if missing and routes_by_fn.get(key):
            out.append({"function": fn["name"], "file": fn["file"], "missing_lines": missing,
                        "routes": sorted(routes_by_fn[key])})
    return sorted(out, key=lambda g: (-len(g["missing_lines"]), g["function"]))


SAVED = "code_coverage.json"


def save(project_dir: Path, rep: Dict[str, Any], label: str = "") -> Path:
    """Keep the latest coverage numbers for the report's coverage dashboard (test_execution/code_coverage.json)."""
    from datetime import datetime, timezone
    path = Path(project_dir) / "test_execution" / SAVED
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: rep.get(k) for k in ("statement_pct", "branch_pct", "statements", "branches", "covered_branches")}
    keep["uncovered_critical"] = [{k: u[k] for k in ("function", "file")} | {"lines": len(u["missing_lines"])}
                                  for u in rep.get("uncovered_critical") or []][:20]
    keep["measured_at"] = datetime.now(timezone.utc).isoformat()
    keep["label"] = label
    path.write_text(json.dumps(keep, indent=2), encoding="utf-8")
    return path


def gap_round(project_dir: Path, rep: Dict[str, Any], max_routes: Optional[int] = None) -> Dict[str, Any]:
    """Generate API tests for the routes that reach uncovered code (prefix gap_, registered like the API specs)."""
    from tools.whitebox import api_tests
    project_dir = Path(project_dir)
    code = json.loads((project_dir / "test_comprehension" / "code_rules.json").read_text(encoding="utf-8"))
    found = gaps(rep, code)
    routes: List[str] = []
    for g in found:
        for r in g["routes"]:
            if r not in routes:
                routes.append(r)
    if max_routes:
        routes = routes[:max_routes]
    files, stats = api_tests.generate(project_dir, only_routes=set(routes), prefix="gap", force=True)
    return {"gaps": found, "routes": routes, "files": [str(f) for f in files], "stats": stats}
