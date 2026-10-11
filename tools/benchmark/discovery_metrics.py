"""
discovery_metrics.py — Phase 2 acceptance metrics for deep discovery (no LLM).

    python -m tools.benchmark.discovery_metrics --app buggy_shop [--port 8790] [--repeat 3]
           [--no-scan-time] [--out benchmarks/results/<date>_buggy_shop_discovery]

Starts the benchmark app (bug-free), materialises a scratch project, runs deep discovery, and scores it
against the app's hand-labelled ground truth:

    element_recall        elements.yaml entries found in app_map.json states (gated on reachability: link)
    constraint_capture    DOM-declared constraints in elements.yaml equal to the captured values
    page_coverage         `link` page templates present as app_map states (per role)
    oracle_match          validation_messages.yaml messages observed in form_model.json
    scan_time             per module URL: element-collection time, classic vs deep (median of --repeat)

The scoring functions are pure (unit-tested with synthetic artifacts); only main() touches a browser.
"""

import argparse
import dataclasses
import datetime as _dt
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import yaml

from tools.benchmark.apps import APPS, REPO_ROOT


# ── ground truth ─────────────────────────────────────────────────────────

def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def expand_pages(truth: Dict[str, Any]) -> List[Dict[str, Any]]:
    """elements.yaml pages with their frame elements prepended (frames are listed once per role)."""
    frames = truth.get("frames") or {}
    out = []
    for page in truth.get("pages") or []:
        els = [{"testid": t} for t in frames.get(page.get("frame"), [])] if page.get("frame") else []
        els += list(page.get("elements") or [])
        out.append({**page, "elements": els})
    return out


# ── scoring (pure) ───────────────────────────────────────────────────────

def _states_for(app_map: Dict[str, Any], template: str, role: str) -> List[Dict[str, Any]]:
    return [s for s in app_map.get("states") or [] if s.get("url_template") == template and role in (s.get("roles") or [])]


def _testid(el: Dict[str, Any]) -> Optional[str]:
    return (el.get("attribute_locators") or {}).get("testid")


def _find(states: List[Dict[str, Any]], testid: str) -> Tuple[int, Optional[Dict[str, Any]]]:
    best, first = 0, None
    for s in states:
        hits = [e for e in s.get("elements") or [] if _testid(e) == testid]
        if len(hits) > best:
            best, first = len(hits), hits[0]
    return best, first


def element_recall(app_map: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    by_reach: Dict[str, Dict[str, int]] = {}
    missing: List[Dict[str, Any]] = []
    for page in expand_pages(truth):
        reach = page.get("reachability", "link")
        states = _states_for(app_map, page["template"], page["role"])
        for el in page["elements"]:
            want = int(el.get("count", 1))
            got, _ = _find(states, el["testid"])
            bucket = by_reach.setdefault(reach, {"expected": 0, "found": 0})
            bucket["expected"] += want
            bucket["found"] += min(got, want)
            if got < want:
                missing.append({"template": page["template"], "role": page["role"], "testid": el["testid"],
                                "reachability": reach, "expected": want, "found": got})
    link = by_reach.get("link", {"expected": 0, "found": 0})
    total_exp = sum(b["expected"] for b in by_reach.values())
    total_found = sum(b["found"] for b in by_reach.values())
    return {
        "recall_link_pct": round(100 * link["found"] / link["expected"], 1) if link["expected"] else None,
        "recall_all_pct": round(100 * total_found / total_exp, 1) if total_exp else None,
        "by_reachability": by_reach, "missing": missing,
    }


def _constraint_value(captured: Dict[str, Any], key: str):
    if key == "options_values":
        return [o.get("value") for o in captured.get("options") or []]
    return captured.get(key)


def constraint_capture(app_map: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    checked = ok = 0
    mismatches: List[Dict[str, Any]] = []
    for page in expand_pages(truth):
        if page.get("reachability", "link") != "link":
            continue
        states = _states_for(app_map, page["template"], page["role"])
        for el in page["elements"]:
            expected = el.get("constraints") or {}
            if not expected:
                continue
            _, found = _find(states, el["testid"])
            captured = (found or {}).get("constraints") or {}
            for key, want in expected.items():
                checked += 1
                got = _constraint_value(captured, key)
                if got == want:
                    ok += 1
                else:
                    mismatches.append({"template": page["template"], "testid": el["testid"], "constraint": key,
                                       "expected": want, "captured": got})
    return {"checked": checked, "captured": ok, "pct": round(100 * ok / checked, 1) if checked else None,
            "mismatches": mismatches}


def page_coverage(app_map: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    wanted = sorted({(p["template"], p["role"]) for p in truth.get("pages") or [] if p.get("reachability", "link") == "link"})
    missing = [{"template": t, "role": r} for t, r in wanted if not _states_for(app_map, t, r)]
    deep_only = sorted({p["template"] for p in truth.get("pages") or [] if p.get("reachability") == "deep_link"})
    return {"expected": len(wanted), "covered": len(wanted) - len(missing),
            "pct": round(100 * (len(wanted) - len(missing)) / len(wanted), 1) if wanted else None,
            "missing": missing, "deep_link_only": deep_only,
            "templates_in_app_map": sorted({s["url_template"] for s in app_map.get("states") or []})}


def oracle_match(form_model: Dict[str, Any], truth: Dict[str, Any]) -> Dict[str, Any]:
    expected = matched = 0
    misses: List[Dict[str, Any]] = []
    for spec in truth.get("forms") or []:
        forms = [f for f in form_model.get("forms") or []
                 if f.get("url_template") == spec["template"] and f.get("dom_id") == spec["form"]]
        for exp in spec.get("expected") or []:
            expected += 1
            hit = False
            for f in forms:
                if exp.get("field"):
                    field = next((x for x in f.get("fields") or [] if x.get("name") == exp["field"]), None)
                    obs = ((field or {}).get("observed_messages") or {}).get(exp["probe"]) or {}
                    hit = obs.get("text") == exp["text"]
                else:
                    hit = any(p.get("probe") == exp["probe"] and any(e.get("text") == exp["text"] for e in p.get("visible_errors") or [])
                              for p in f.get("probes") or [])
                if hit:
                    break
            if hit:
                matched += 1
            else:
                misses.append({**exp, "template": spec["template"], "form": spec["form"], "form_found": bool(forms)})
    return {"expected": expected, "matched": matched, "pct": round(100 * matched / expected, 1) if expected else None,
            "misses": misses}


# ── scan time (browser) ──────────────────────────────────────────────────

def measure_scan_time(modules: List[Dict[str, Any]], repeat: int = 3) -> Dict[str, Any]:
    from tools.discovery.deep.config import DiscoveryConfig
    from tools.playwright_scanner import PlaywrightScanner

    deep_cfg = DiscoveryConfig(deep=True).model_dump()
    rows = []
    for m in modules:
        row: Dict[str, Any] = {"module": m.get("id"), "url": m.get("url")}
        for mode in ("classic", "deep"):
            scan_s, wall_s, counts = [], [], []
            for _ in range(repeat):
                t = time.monotonic()
                res = PlaywrightScanner().scan_page(m["url"], setup_steps=m.get("setup"),
                                                    deep_config=deep_cfg if mode == "deep" else None)
                wall_s.append(time.monotonic() - t)
                scan_s.append(res.get("element_scan_s") or 0.0)
                counts.append(res.get("element_count"))
            row[mode] = {"element_scan_s_median": round(statistics.median(scan_s), 3),
                         "scan_page_s_median": round(statistics.median(wall_s), 3), "elements": counts[0]}
        row["deep_not_slower"] = row["deep"]["element_scan_s_median"] <= row["classic"]["element_scan_s_median"]
        rows.append(row)
    return {"repeat": repeat, "modules": rows, "all_deep_not_slower": all(r["deep_not_slower"] for r in rows)}


# ── report ───────────────────────────────────────────────────────────────

def render_md(result: Dict[str, Any]) -> str:
    r = result
    lines = [f"# Deep discovery metrics — {r['app']} ({r['date']})", "",
             "| Metric | Result |", "|---|---|"]
    er, cc, pc, om = r["element_recall"], r["constraint_capture"], r["page_coverage"], r["oracle_match"]
    lines.append(f"| Element recall (link-reachable) | {er['recall_link_pct']}% |")
    lines.append(f"| Element recall (all labelled) | {er['recall_all_pct']}% |")
    lines.append(f"| Constraint capture | {cc['captured']}/{cc['checked']} = {cc['pct']}% |")
    lines.append(f"| Page coverage (link-reachable templates × role) | {pc['covered']}/{pc['expected']} = {pc['pct']}% |")
    lines.append(f"| Observed validation messages matching the app | {om['matched']}/{om['expected']} = {om['pct']}% |")
    d = r.get("deep_discovery") or {}
    lines.append(f"| Deep discovery run | {d.get('duration_s')} s, {d.get('states')} states, {d.get('forms')} forms, "
                 f"{d.get('probes')} probes, {d.get('endpoints')} endpoints |")
    st = r.get("scan_time")
    if st:
        lines += ["", "## Scan time (element collection, median of %d)" % st["repeat"], "",
                  "| Module | Classic s | Deep s | Classic elements | Deep elements | Deep ≤ classic |", "|---|---|---|---|---|---|"]
        for row in st["modules"]:
            lines.append(f"| {row['module']} | {row['classic']['element_scan_s_median']} | {row['deep']['element_scan_s_median']} | "
                         f"{row['classic']['elements']} | {row['deep']['elements']} | {'yes' if row['deep_not_slower'] else 'NO'} |")
    for title, items in (("Missing elements", er["missing"]), ("Constraint mismatches", cc["mismatches"]),
                         ("Missing pages", pc["missing"]), ("Unmatched messages", om["misses"])):
        if items:
            lines += ["", f"## {title}", ""] + [f"- `{json.dumps(i, ensure_ascii=False)}`" for i in items]
    return "\n".join(lines) + "\n"


def score_artifacts(app_name: str, comp_dir: str) -> Dict[str, Any]:
    """Score existing deep-discovery artifacts (used by the benchmark runner too)."""
    app = APPS[app_name]
    truth_el = load_yaml(app.elements_yaml)
    truth_msg = load_yaml(app.validation_messages_yaml)
    from contracts.artifacts import load_payload
    app_map = load_payload("app_map", os.path.join(comp_dir, "app_map.json"), {})
    form_model = load_payload("form_model", os.path.join(comp_dir, "form_model.json"), {})
    return {"element_recall": element_recall(app_map, truth_el),
            "constraint_capture": constraint_capture(app_map, truth_el),
            "page_coverage": page_coverage(app_map, truth_el),
            "oracle_match": oracle_match(form_model, truth_msg)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", default="buggy_shop")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--no-scan-time", action="store_true")
    ap.add_argument("--out", default=None, help="output path without extension")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")   # Windows consoles: cp1252 cannot print the report's symbols
    except (AttributeError, ValueError):
        pass

    from tools import constants
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.materialize import materialize_project
    from tools.discovery.deep.service import ensure_app_discovery
    from tools.project_manifest import load_project_manifest

    app = dataclasses.replace(APPS[args.app], project_name=APPS[args.app].project_name + "_discovery")
    date = _dt.date.today().isoformat()
    with AppServer(app, port=args.port) as srv:
        materialize_project(app, constants.PROJECTS_BASE, srv.base_url, clean=True)
        deep = ensure_app_discovery(app.project_name, force=True, log=print)
        if deep.get("status") != "success":
            print(json.dumps(deep, indent=2))
            return 1
        comp_dir = os.path.dirname(deep["paths"]["app_map"])
        result = {"app": args.app, "date": date, "deep_discovery": {k: v for k, v in deep.items() if k != "paths"},
                  **score_artifacts(args.app, comp_dir)}
        if not args.no_scan_time:
            manifest = load_project_manifest(app.project_name)
            result["scan_time"] = measure_scan_time(manifest.get("modules") or [], repeat=args.repeat)
    out = args.out or os.path.join(REPO_ROOT, "benchmarks", "results", f"{date}_{args.app}_discovery")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open(out + ".md", "w", encoding="utf-8") as f:
        f.write(render_md(result))
    print(render_md(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
