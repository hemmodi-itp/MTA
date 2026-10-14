"""
nfr_bench.py — Phase 7 acceptance on buggy_shop: the generated non-functional specs (tools/nonfunctional) run on
the correct app and with each seeded non-functional bug. A bug is DETECTED when its run has a failing finding
(rule @ test) the clean run does not have — findings the correct app already has are reported, not credited.

    python -m tools.benchmark.nfr_bench [--types accessibility,performance] [--out PATH]

Needs: Phase 2 discovery artifacts of bench_buggy_shop (app_map / form_model / baseline / requirements) recorded
against http://127.0.0.1:8765 (the app is started on that port), and @axe-core/playwright installed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from tools.constants import PROJECTS_BASE

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "bench_p7_nfr"
SOURCE = "bench_buggy_shop"
PORT = 8765
# seeded bug -> the test types expected to catch it
TARGETS = {"BUG_08": ["accessibility"], "BUG_09": ["performance"], "BUG_07": ["resilience"]}
TYPES = ["accessibility", "visual", "performance", "security_passive", "compatibility", "resilience", "i18n"]
SPEC_OF = {"accessibility": "nfr_a11y", "visual": "nfr_visual", "performance": "nfr_perf",
           "security_passive": "nfr_security_", "compatibility": "nfr_responsive", "resilience": "nfr_resilience",
           "i18n": "nfr_i18n"}


def build(types: List[str]) -> Path:
    from tools.nonfunctional.generate import generate, register
    src, pdir = Path(PROJECTS_BASE) / SOURCE, Path(PROJECTS_BASE) / PROJECT
    shutil.rmtree(pdir, ignore_errors=True)
    (pdir / "test_comprehension").mkdir(parents=True)
    for name in ("app_map", "form_model", "baseline", "requirements", "api_inventory"):
        f = src / "test_comprehension" / f"{name}.json"
        if f.exists():
            shutil.copy(f, pdir / "test_comprehension" / f.name)
    cfg = yaml.safe_load((src / "project.yaml").read_text(encoding="utf-8"))
    cfg["project"]["name"] = PROJECT
    cfg["test_types"] = {t: t in types for t in TYPES}
    cfg["nfr"] = {"compatibility": {"viewports": [375, 1280]},
                  "i18n": {"locales": ["en-US", "ar-EG"], "timezones": ["UTC"]},
                  "performance": {"budget": {"ttfb_ms": 1500, "load_ms": 3000}}}
    cfg.setdefault("execution", {})["role_auth_max_age_minutes"] = 0
    (pdir / "project.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    register(pdir, generate(pdir))
    return pdir


def _findings(result: dict) -> List[str]:
    """Failing findings of one test: rule @ test title (from the attached findings JSON, else the first error line)."""
    out = []
    for a in result.get("attachments") or []:
        if str(a.get("name", "")).endswith("-findings.json") and a.get("path"):
            try:
                with open(a["path"], encoding="utf-8") as fh:
                    out += [f"{x['rule']} — {x.get('message', '')[:90]}" for x in json.load(fh) if x.get("level", "fail") == "fail"]
            except (OSError, ValueError, KeyError):
                pass
    if not out and result.get("status") not in ("success", "flaky", "skipped"):
        err = " ".join(result.get("errors") or [])
        rules = sorted(set(re.findall(r'"rule":\s*"([^"]+)"', err))) or [err.strip().splitlines()[0][:120] if err.strip() else "failed"]
        out = rules
    return [f"{r} @ {result.get('test_title')}" for r in out]


def run(spec_globs: List[str], bugs: List[str]) -> Dict[str, Any]:
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS
    server = AppServer(APPS["buggy_shop"], port=PORT, bugs=bugs).start()
    try:
        out = UIExecutionAgent().execute({"project_name": PROJECT, "headless": True, "spec_files": spec_globs}, {})
    finally:
        server.stop()
    results = out.get("results") or []
    return {"passed": out.get("passed"), "failed": out.get("failed"), "tests": len(results),
            "findings": sorted({f for r in results for f in _findings(r)}),
            "status_by_test": {r["test_title"]: r["status"] for r in results}}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--types", default=",".join(TYPES))
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / f"{date.today().isoformat()}_buggy_shop_phase7_nfr"))
    args = ap.parse_args(argv)
    os.chdir(ROOT)
    types = [t for t in args.types.split(",") if t]
    pdir = build(types)
    nfr_dir = pdir / "test_creation" / "test_scripts" / "nfr"
    specs = {t: sorted(f"nfr/{p.name}" for p in nfr_dir.glob("*.spec.ts") if p.name.startswith(SPEC_OF[t])) for t in types}
    all_specs = sorted({s for v in specs.values() for s in v})
    result: Dict[str, Any] = {"date": date.today().isoformat(), "types": types, "specs": specs}
    run(["nfr/nfr_visual.spec.ts"], []) if "visual" in types else None      # first visual run records the baselines
    clean = run(all_specs, [])
    result["clean"] = clean
    result["bugs"] = {}
    for bug, kinds in TARGETS.items():
        kinds = [k for k in kinds if k in types]
        if not kinds:
            continue
        files = sorted({s for k in kinds for s in specs[k]})
        got = run(files, [bug])
        new = [f for f in got["findings"] if f not in set(clean["findings"])]
        result["bugs"][bug] = {"types": kinds, "detected": bool(new), "new_findings": new[:20],
                               "failed": got["failed"], "tests": got["tests"]}
        print(f"{bug} ({', '.join(kinds)}): {'DETECTED' if new else 'missed'} — {new[:3]}")
    result["summary"] = {"detected": sum(1 for b in result["bugs"].values() if b["detected"]),
                         "targets": len(result["bugs"]), "clean_failures": clean["failed"],
                         "clean_findings": len(clean["findings"])}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out + ".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    Path(args.out + ".md").write_text(to_markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return 0


def to_markdown(r: Dict[str, Any]) -> str:
    s = r["summary"]
    lines = [f"# Phase 7 non-functional benchmark — buggy_shop ({r['date']})", "",
             "Generated NFR specs (tools/nonfunctional/generate.py) from bench_buggy_shop's Phase 2 discovery, run "
             "through UIExecutionAgent on the correct app and with each seeded non-functional bug. Detected = the bug "
             "run has a failing finding the clean run does not.", "",
             f"Types: {', '.join(r['types'])}. Tests: {r['clean']['tests']}.", "",
             "| Seeded bug | Checked by | Detected | New finding(s) |", "|---|---|---|---|"]
    for bug, b in r["bugs"].items():
        lines.append(f"| {bug} | {', '.join(b['types'])} | {'yes' if b['detected'] else '**no**'} | "
                     f"{'<br>'.join(x.replace('|', '/') for x in b['new_findings'][:3]) or '—'} |")
    lines += ["", f"**{s['detected']}/{s['targets']} detected.**", "",
              f"## Findings on the correct app ({s['clean_findings']}; {s['clean_failures']} failing test(s))", "",
              "Real issues of the benchmark app itself (not seeded bugs) — e.g. missing security headers:", ""]
    lines += [f"- {f}" for f in r["clean"]["findings"][:40]]
    if len(r["clean"]["findings"]) > 40:
        lines.append(f"- … {len(r['clean']['findings']) - 40} more (see the .json)")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
