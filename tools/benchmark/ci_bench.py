"""
ci_bench.py — Phase 10 end to end on buggy_shop: the CI stages (tools/ci/run.py) against a real app and Playwright.

    python -m tools.benchmark.ci_bench [--out PATH]

Scenarios (each checks the stage's exit code and what it did):
  A  app down                         pr      -> exit 3, environment_blocked, no tests run
  B  app up, fresh suite              nightly -> burn-in admits the specs, order check clean, fingerprint saved, exit 0
  C  nothing changed / one spec edited  pr    -> 0 impacted, only the smoke test runs / smoke + that spec's tests, exit 0
  D  a consistently failing test       release -> exit 1; the same test quarantined -> exit 0, reported as quarantined
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from tools.constants import PROJECTS_BASE

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "bench_p10_ci"
PORT = 8775
CANARY = "C/test_ci_canary.spec.ts"
CANARY_TITLE = "checkout total matches the cart"
SMOKE_SPEC_PREFIX = "test_L_"          # the one spec kept @smoke


def build() -> Path:
    from tools.benchmark import healing_bench as hb
    hb.PROJECT = PROJECT
    base = f"http://127.0.0.1:{PORT}"
    pdir = Path(hb.build_project(base, {k: v for k, v in hb.SPECS.items() if "BUG" not in k}))
    raw = yaml.safe_load((pdir / "project.yaml").read_text(encoding="utf-8"))
    raw["health_check"] = {"enabled": True, "timeout_s": 10, "auth_url": "/products/new",
                           "seed": [{"path": "/api/products", "role": "user", "status": 200,
                                     "contains": "The Pragmatic Coder"}]}
    (pdir / "project.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    # the healing fixture tags every test @smoke, and a PR always runs the smoke tests — keep @smoke on the login
    # test only, so a PR run shows the selection (C) instead of running the whole suite as "smoke"
    for spec in (pdir / "test_creation" / "test_scripts").rglob("*.spec.ts"):
        if not spec.name.startswith(SMOKE_SPEC_PREFIX):
            spec.write_text(spec.read_text(encoding="utf-8").replace(" @smoke", ""), encoding="utf-8")
    return pdir


def add_canary(pdir: Path) -> None:
    """A test that always fails (stands in for a broken / flaky test) — admitted, so it gates."""
    from contracts.artifacts import load_payload, save_artifact
    spec = pdir / "test_creation" / "test_scripts" / CANARY
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("import { test, expect } from '@playwright/test';\n\n"
                    f"test({json.dumps(CANARY_TITLE)}, async () => {{\n  expect(41).toBe(42);\n}});\n", encoding="utf-8")
    path = str(pdir / "test_creation" / "test_suite.json")
    suite = load_payload("test_suite", path)
    suite["specs"].append({"spec_id": "C_CI_001", "file": CANARY, "module_id": "C", "status": "admitted"})
    save_artifact("test_suite", path, suite)


def stage(name: str, **kw) -> Dict[str, Any]:
    from tools.ci.run import run_stage
    t0 = time.time()
    s = run_stage(PROJECT, name, **kw)
    ex = s.get("execution") or {}
    out = {"stage": name, "exit_code": s["exit_code"], "status": ex.get("status"), "passed": ex.get("passed"),
           "failed": ex.get("failed"), "seconds": round(time.time() - t0, 1)}
    for k in ("selection", "admission", "order_check", "fingerprint", "health"):
        if s.get(k) is not None:
            out[k] = s[k]
    if ex.get("error"):
        out["error"] = str(ex["error"])[:300]
    print(f"  {name}: exit {out['exit_code']} ({out['status']}, {out['passed']} passed, {out['failed']} failed, {out['seconds']}s)")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS
    from tools.execution import quarantine as qz
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / f"{date.today().isoformat()}_buggy_shop_phase10_ci"))
    args = ap.parse_args(argv)
    os.chdir(ROOT)
    pdir = build()
    r: Dict[str, Any] = {"date": date.today().isoformat(), "scenarios": {}}
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'ok' if ok else 'FAIL'}] {name} {detail if not ok else ''}")

    print("A  app down")
    a = stage("pr")
    r["scenarios"]["A_app_down"] = a
    check("A: exit 3 when the app is down", a["exit_code"] == 3, a)
    check("A: no test ran", not a.get("passed") and not a.get("failed"))

    srv = AppServer(APPS["buggy_shop"], port=PORT).start()
    try:
        print("B  nightly on a fresh suite")
        b = stage("nightly", order_check=True)
        r["scenarios"]["B_nightly"] = b
        adm = b.get("admission") or {}
        check("B: exit 0", b["exit_code"] == 0, b)
        check("B: burn-in admitted every new test", adm.get("admitted") and not adm.get("quarantined") and not adm.get("failing"), adm)
        check("B: order check found no order-dependent test", not (b.get("order_check") or {}).get("order_dependent"),
              b.get("order_check"))
        check("B: fingerprint saved", (pdir / "test_execution" / "fingerprint.json").is_file())

        print("C  pull requests")
        c1 = stage("pr")
        check("C1: nothing changed -> no impacted test", (c1.get("selection") or {}).get("impacted") == 0, c1.get("selection"))
        ran = lambda s: (s.get("passed") or 0) + (s.get("failed") or 0)      # noqa: E731
        check("C1: only the smoke test ran", ran(c1) == 1, {"ran": ran(c1)})
        check("C1: exit 0", c1["exit_code"] == 0, c1)
        spec = next((pdir / "test_creation" / "test_scripts" / "P").glob("*.spec.ts"))
        spec.write_text(spec.read_text(encoding="utf-8") + "\n// edited by the PR\n", encoding="utf-8")
        c2 = stage("pr")
        check("C2: the edited spec's tests are selected and run",
              (c2.get("selection") or {}).get("impacted", 0) >= 1 and (c2.get("passed") or 0) >= 1, c2.get("selection"))
        impacted = (c2.get("selection") or {}).get("impacted", 0)
        check("C2: only smoke + impacted tests ran, fewer than nightly", ran(c2) == 1 + impacted < ran(b),
              {"pr": ran(c2), "impacted": impacted, "nightly": ran(b)})
        check("C2: exit 0", c2["exit_code"] == 0, c2)
        r["scenarios"]["C_pr"] = {"unchanged": c1, "spec_edited": c2}

        print("D  release with a failing test, then quarantined")
        add_canary(pdir)
        d1 = stage("release")
        check("D1: a failing gating test -> exit 1", d1["exit_code"] == 1, d1)
        q = qz.load(str(pdir))
        qz.add(q, f"{CANARY} :: {CANARY_TITLE}", "manual", "expect(received).toBe(expected)", owner="qa")
        qz.save(str(pdir), q)
        d2 = stage("release")
        check("D2: the same test quarantined -> exit 0", d2["exit_code"] == 0, d2)
        rep = sorted((pdir / "test_execution" / "reports" / "json").glob(f"*_{PROJECT}.json"), key=os.path.getmtime)
        quarantined = None
        for p in reversed(rep):
            try:
                quarantined = json.loads(p.read_text(encoding="utf-8")).get("quarantine")
            except (OSError, ValueError):
                continue
            if quarantined is not None:
                break
        check("D2: the report lists it as quarantined", quarantined and CANARY_TITLE in json.dumps(quarantined), quarantined)
        r["scenarios"]["D_release"] = {"failing": d1, "quarantined": d2, "report_quarantine": quarantined}
    finally:
        srv.stop()

    r["checks"] = checks
    r["passed"] = sum(c["ok"] for c in checks)
    r["total"] = len(checks)
    Path(args.out + ".json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    lines = [f"# Phase 10 CI benchmark — buggy_shop ({r['date']})", "",
             f"**{r['passed']}/{r['total']} checks passed**", "", "| Check | Result |", "|---|---|"]
    lines += [f"| {c['check']} | {'pass' if c['ok'] else 'FAIL'} |" for c in checks]
    lines += ["", "| Stage run | Exit | Status | Passed | Failed | Seconds |", "|---|---|---|---|---|---|"]
    for sc, v in r["scenarios"].items():
        for sub, s in ({sc: v} if "stage" in v else v).items():
            if isinstance(s, dict) and "stage" in s:
                lines.append(f"| {sub} ({s['stage']}) | {s['exit_code']} | {s['status']} | {s['passed']} | {s['failed']} | {s['seconds']} |")
    Path(args.out + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{r['passed']}/{r['total']} checks passed -> {args.out}.json")
    return 0 if r["passed"] == r["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
