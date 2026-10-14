"""
whitebox_bench.py — Phase 8 acceptance on buggy_shop (real Chromium + Playwright; app run under coverage.py).

  1. white-box rules from the app's source (code_rules.json) and the generated API suite: endpoint coverage
  2. coverage of a UI-only baseline suite (the Phase 6 benchmark's functional specs): statements / branches,
     plus V8 JS function coverage
  3. one gap round: API tests for exactly the routes that reach uncovered code; baseline + gap re-measured
  4. the API suite against each seeded bug — every "server accepts what the client rejects" bug must fail a test
  5. (--mutants N) mutation score of the API suite on validate_product / parse_quantity

    python -m tools.benchmark.whitebox_bench [--mutants 0] [--out PATH]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from tools.constants import PROJECTS_BASE

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "bench_p8_wb"
PORT = 8765
BUGS = ["BUG_02", "BUG_01", "BUG_18", "BUG_21", "BUG_17", "BUG_16", "BUG_04", "BUG_07", "BUG_13"]
MISMATCH = ["BUG_02"]          # bugs.yaml category server_client_mismatch


def build() -> Path:
    from tools.benchmark import healing_bench as hb
    from tools.whitebox import api_tests, extract
    hb.PROJECT = PROJECT
    base = f"http://127.0.0.1:{PORT}"
    pdir = Path(hb.build_project(base, hb.SPECS))
    src = Path(PROJECTS_BASE) / "bench_buggy_shop" / "test_comprehension"
    comp = pdir / "test_comprehension"
    comp.mkdir(parents=True, exist_ok=True)
    for n in ("app_map", "api_inventory", "requirements", "form_model"):
        if (src / f"{n}.json").exists():
            shutil.copy(src / f"{n}.json", comp)
    raw = yaml.safe_load((pdir / "project.yaml").read_text(encoding="utf-8"))
    raw["safety"]["allow_destructive"] = True
    raw["test_types"] = {"api": True}
    raw["white_box"] = {"enabled": True, "source_dir": "benchmarks/apps/buggy_shop"}
    raw["auth"]["roles"]["admin"] = {"strategy": "setup", "steps": [
        {"goto": f"{base}/login"}, {"fill": {"selector": "input[name=username]", "value": "admin"}},
        {"fill": {"selector": "input[name=password]", "value": "admin-pass-1"}},
        {"click": "#login-form button[type=submit]"}, {"wait": 300}]}
    raw["api_tests"] = {"ownership": [{"path": "/api/orders/1", "owner": "admin", "other": "user"},
                                      {"path": "/orders/1", "owner": "admin", "other": "user"}]}
    (pdir / "project.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    extract.run(pdir, root=ROOT)
    return pdir


def _specs(pdir: Path, pattern: str) -> List[str]:
    scripts = pdir / "test_creation" / "test_scripts"
    return sorted(Path(p).relative_to(scripts).as_posix() for p in glob.glob(str(scripts / pattern), recursive=True))


def run(specs: List[str], bugs: List[str] = (), coverage_data: Optional[str] = None,
        js_dir: Optional[str] = None) -> Dict[str, Any]:
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS
    if js_dir:
        os.environ["MTA_JS_COVERAGE"] = js_dir
    srv = AppServer(APPS["buggy_shop"], port=PORT, bugs=list(bugs), coverage_data=coverage_data).start()
    try:
        out = UIExecutionAgent().execute({"project_name": PROJECT, "headless": True, "spec_files": specs}, {})
    finally:
        srv.stop()
        os.environ.pop("MTA_JS_COVERAGE", None)
    res = out.get("results") or []
    return {"passed": out.get("passed"), "failed": out.get("failed"), "tests": len(res),
            "failing": sorted(r["test_title"] for r in res if r.get("status") not in ("success", "skipped", "flaky"))}


def main(argv: Optional[List[str]] = None) -> int:
    from tools.whitebox import api_tests, coverage_gap, js_coverage
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mutants", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / f"{date.today().isoformat()}_buggy_shop_phase8_whitebox"))
    args = ap.parse_args(argv)
    os.chdir(ROOT)
    pdir = build()
    code = json.loads((pdir / "test_comprehension" / "code_rules.json").read_text(encoding="utf-8"))
    result: Dict[str, Any] = {"date": date.today().isoformat(),
                              "rules": len(code["rules"]), "routes": len(code["routes"]),
                              "contract_findings": code.get("contract")}
    work = Path(tempfile.mkdtemp(prefix="mta-wb-"))
    ui = _specs(pdir, "[LP]/*.spec.ts")
    ui = [s for s in ui if "BUG_" not in s]

    # 2. baseline coverage
    base_cov = str(work / "base.coverage")
    result["baseline_run"] = run(ui, coverage_data=base_cov, js_dir=str(work / "js0"))
    rep0 = coverage_gap.report(base_cov, code)
    result["baseline"] = {k: rep0[k] for k in ("statement_pct", "branch_pct", "statements", "branches", "covered_branches")}
    result["baseline"]["js"] = js_coverage.summarize(str(work / "js0"))
    result["uncovered_critical"] = rep0["uncovered_critical"][:15]

    # 3. one gap round
    gap = coverage_gap.gap_round(pdir, rep0)
    result["gap_round"] = {"routes": gap["routes"], "gaps": len(gap["gaps"]), "files": [Path(f).name for f in gap["files"]]}
    gap_cov = str(work / "gap.coverage")
    result["gap_run"] = run(ui + _specs(pdir, "api/gap_*.spec.ts"), coverage_data=gap_cov, js_dir=str(work / "js1"))
    rep1 = coverage_gap.report(gap_cov, code)
    coverage_gap.save(pdir, rep1, "UI + one gap round")
    result["after_gap"] = {k: rep1[k] for k in ("statement_pct", "branch_pct", "statements", "branches", "covered_branches")}

    # 1. full API suite + endpoint coverage
    files, stats = api_tests.generate(pdir)
    api_tests.register(pdir, files)
    result["api"] = stats
    api_specs = _specs(pdir, "api/api_*.spec.ts")
    clean = run(api_specs)
    result["api_clean"] = clean

    # 4. seeded bugs
    result["bugs"] = {}
    for bug in BUGS:
        r = run(api_specs, [bug])
        new = [t for t in r["failing"] if t not in clean["failing"]]
        result["bugs"][bug] = {"detected": bool(new), "failing": new[:6], "mismatch": bug in MISMATCH}
        print(f"{bug}: {'DETECTED' if new else 'missed'} {new[:2]}")

    # 5. mutation score (scheduled job; optional here)
    if args.mutants:
        from tools.whitebox import mutation
        target = [s for s in api_specs if "api_products" in s or "api_cart" in s or s.endswith("api_products.spec.ts")]

        def suite_passes() -> bool:
            return run(target)["failed"] == 0
        m = mutation.run(str(ROOT / "benchmarks" / "apps" / "buggy_shop" / "app.py"),
                         ["validate_product", "parse_quantity"], suite_passes, max_mutants=args.mutants)
        result["mutation"] = {k: m[k] for k in ("mutants", "killed", "survived", "score_pct", "survivors")}

    s = result
    s["summary"] = {
        "endpoint_coverage_pct": stats.get("endpoint_coverage_pct"),
        "branch_pct_baseline": rep0["branch_pct"], "branch_pct_after_gap": rep1["branch_pct"],
        "statement_pct_baseline": rep0["statement_pct"], "statement_pct_after_gap": rep1["statement_pct"],
        "mismatch_bugs_caught": sum(1 for b in MISMATCH if s["bugs"].get(b, {}).get("detected")),
        "mismatch_bugs": len(MISMATCH),
        "bugs_caught": sum(1 for b in s["bugs"].values() if b["detected"]), "bugs": len(s["bugs"]),
    }
    s["summary"]["pass"] = (bool(stats.get("endpoint_coverage_pct")) and stats["endpoint_coverage_pct"] >= 90
                            and (rep1["branch_pct"] or 0) > (rep0["branch_pct"] or 0)
                            and s["summary"]["mismatch_bugs_caught"] == len(MISMATCH))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out + ".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    Path(args.out + ".md").write_text(to_markdown(result), encoding="utf-8")
    print(json.dumps(s["summary"], indent=2))
    if not os.environ.get("MTA_KEEP_E2E"):
        shutil.rmtree(pdir, ignore_errors=True)
    return 0


def to_markdown(r: Dict[str, Any]) -> str:
    s = r["summary"]
    b0, b1 = r["baseline"], r["after_gap"]
    lines = [f"# Phase 8 white-box benchmark — buggy_shop ({r['date']})", "",
             f"White-box rules from `benchmarks/apps/buggy_shop` source: {r['routes']} routes, {r['rules']} rules "
             "(each cites file:line). App run under coverage.py (branch).", "",
             "| KPI | Result | Target |", "|---|---|---|",
             f"| API endpoint coverage | **{s['endpoint_coverage_pct']}%** of {r['api'].get('endpoints')} | ≥ 90% |",
             f"| Code coverage collected | statements {b0['statement_pct']}%, branches {b0['branch_pct']}% (UI baseline) | yes |",
             f"| One gap round raises branch coverage | **{s['branch_pct_baseline']}% → {s['branch_pct_after_gap']}%** "
             f"(statements {s['statement_pct_baseline']}% → {s['statement_pct_after_gap']}%) | measurable rise |",
             f"| \"Server accepts what the client rejects\" bugs caught by an API test | **{s['mismatch_bugs_caught']}/{s['mismatch_bugs']}** | all |",
             f"| Other seeded bugs caught by the API suite | {s['bugs_caught']}/{s['bugs']} | — |", ""]
    js = b0.get("js") or {}
    lines += [f"Frontend (V8): {js.get('covered')}/{js.get('functions')} JS functions ran in the baseline "
              f"({js.get('function_pct')}%; inline scripts, no source maps).", "",
              f"Gap round: {r['gap_round']['gaps']} function(s) with uncovered lines → API tests for "
              f"{len(r['gap_round']['routes'])} route(s): {', '.join(r['gap_round']['routes'][:12])}.", "",
              "## Seeded bugs vs the API suite", "", "| Bug | Detected | First failing API test(s) |", "|---|---|---|"]
    for bug, b in r["bugs"].items():
        lines.append(f"| {bug}{' (server/client mismatch)' if b['mismatch'] else ''} | {'yes' if b['detected'] else 'no'} | "
                     f"{'<br>'.join(x.replace('|', '/') for x in b['failing'][:2]) or '—'} |")
    if r.get("mutation"):
        m = r["mutation"]
        lines += ["", "## Mutation score (validate_product, parse_quantity)", "",
                  f"{m['killed']}/{m['mutants']} mutants killed — **{m['score_pct']}%**. Survivors:"]
        lines += [f"- line {x['line']} {x['function']}: {x['description']}" for x in m["survivors"]]
    lines += ["", "## Uncovered critical functions after the UI baseline", ""]
    lines += [f"- {u['function']} ({u['file']}): {len(u['missing_lines'])} line(s)" for u in r["uncovered_critical"][:10]]
    if r.get("contract_findings"):
        lines += ["", "## Contract findings (frontend vs backend)", ""]
        lines += [f"- {c['type']}: {c['where']} {c.get('field') or ''} — {c['detail']}" for c in r["contract_findings"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
