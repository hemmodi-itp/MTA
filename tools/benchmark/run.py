"""
run.py — end-to-end MTA benchmark (Phase 0.3 / 0.4).

    python -m tools.benchmark.run --app buggy_shop
    python -m tools.benchmark.run --app buggy_shop --skip-generate --no-healing   # no LLM spend
    python -m tools.benchmark.run --app buggy_shop --bugs BUG_01,BUG_07 --repeat 3
    python -m tools.benchmark.run --app buggy_shop --rescore benchmarks/results/<file>.json
                                  # re-score a saved run (e.g. after filling pricing.yaml)

Flow:
  1. materialise application_assets/projects/<bench project> from the app template
  2. start the app with every bug OFF
  3. generate: `python main.py --project <bench project>` (the unchanged full workflow)
  4. run the generated suite --repeat times on the bug-free app (false failures, flakiness)
  5. per bug: restart the app with only that bug ON and run the suite again (detection)
  6. heal probe (--with-healing): for each caught bug, heal a scratch copy of the suite
     against the buggy app; a heal that turns a bug-catching test green is a WRONG heal
  7. score -> benchmarks/results/<date>_<app>[_<label>].json + .md, and print the table
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import yaml

from tools.benchmark.app_server import AppServer
from tools.benchmark.apps import APPS, REPO_ROOT, BenchmarkApp, load_acs, load_bugs
from tools.benchmark.materialize import materialize_project
from tools.benchmark.report_md import render_markdown
from tools.benchmark.score import normalize_status, score

PROJECTS_BASE = os.path.join(REPO_ROOT, "application_assets", "projects")
PRICING_PATH = os.path.join(REPO_ROOT, "benchmarks", "pricing.yaml")


def _log(msg: str) -> None:
    print(f"[benchmark {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _settings() -> dict:
    with open(os.path.join(REPO_ROOT, "workflows", "settings.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _pricing() -> Dict[str, Dict[str, float]]:
    if not os.path.exists(PRICING_PATH):
        return {}
    with open(PRICING_PATH, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("models", {}) or {}


# ── generation ────────────────────────────────────────────────────────────────

def _discovery_step_seconds(project: str, since: float) -> Optional[float]:
    """Duration of the `discovery` step in the newest workflow run file written for *project*
    after *since* (epoch seconds) — the per-module discovery time (Phase 2)."""
    import glob

    files = [f for f in glob.glob(os.path.join(REPO_ROOT, "workflow_runs", f"*_{project}_*.json"))
             if os.path.getmtime(f) >= since]
    if not files:
        return None
    try:
        with open(max(files, key=os.path.getmtime), encoding="utf-8") as f:
            trace = json.load(f).get("execution_trace") or []
    except (OSError, ValueError):
        return None
    step = next((t for t in trace if t.get("step") == "discovery"), None)
    return round(step["duration_ms"] / 1000, 1) if step and step.get("duration_ms") is not None else None


def deep_discovery_pass(app, port: int, server_log: str) -> Dict[str, Any]:
    """Phase 2: run deep discovery once, on its OWN app instance, before generation.

    Full-mode validation probes can change the app's in-memory state (an invalid input the app
    wrongly accepts creates data), so generation then starts from a fresh instance. The module
    runs reuse the app_map this pass wrote (same config hash, younger than reuse_minutes)."""
    from tools.discovery.deep.service import ensure_app_discovery

    started = time.monotonic()
    with AppServer(app, port, log_path=server_log):
        result = ensure_app_discovery(app.project_name, force=True, log=_log)
    out: Dict[str, Any] = {"status": result.get("status"), "seconds": round(time.monotonic() - started, 1),
                           **{k: v for k, v in result.items() if k not in ("paths", "status")}}
    if result.get("status") == "success" and os.path.exists(app.elements_yaml):
        from tools.benchmark.discovery_metrics import score_artifacts

        scored = score_artifacts(app.name, os.path.dirname(result["paths"]["app_map"]))
        out["metrics"] = {
            "element_recall_link_pct": scored["element_recall"]["recall_link_pct"],
            "element_recall_all_pct": scored["element_recall"]["recall_all_pct"],
            "constraint_capture_pct": scored["constraint_capture"]["pct"],
            "page_coverage_pct": scored["page_coverage"]["pct"],
            "oracle_match_pct": scored["oracle_match"]["pct"],
        }
    return out


def generate(project: str, modules: List[str], usage_log: str, timeout_s: int,
             workflow: str) -> Tuple[Dict[str, int], float, Dict[str, Optional[float]]]:
    """Run the unchanged pipeline once per module (`main.py --module <id>`), the way
    modular projects are run: without --module, request["url"] is empty and discovery
    silently falls back to BRD-only mode (no DOM scan, no specs) — see
    docs/audit/current_state.md A13. Returns ({module: returncode}, seconds,
    {module: discovery-step seconds})."""
    env = {**os.environ, "MTA_LLM_USAGE_LOG": usage_log, "PYTHONIOENCODING": "utf-8"}
    started = time.monotonic()
    codes: Dict[str, int] = {}
    discovery_s: Dict[str, Optional[float]] = {}
    for module_id in modules:
        module_started = time.time()
        cmd = [sys.executable, "main.py", "--project", project, "--workflow", workflow,
               "--module", module_id, "--force-rediscover"]
        _log(f"generation: {' '.join(cmd)}")
        remaining = max(60, timeout_s - (time.monotonic() - started))
        try:
            codes[module_id] = subprocess.run(cmd, cwd=REPO_ROOT, env=env, timeout=remaining).returncode
        except subprocess.TimeoutExpired:
            codes[module_id] = -1
            _log(f"generation for {module_id} timed out")
        discovery_s[module_id] = _discovery_step_seconds(project, module_started)
    return codes, round(time.monotonic() - started, 1), discovery_s


# ── execution ─────────────────────────────────────────────────────────────────

def _test_id(r: Dict[str, Any]) -> str:
    return f"{str(r.get('spec_file', '')).replace(os.sep, '/')}::{r.get('test_title', '')}"


def run_suite(project: str) -> Tuple[Dict[str, str], List[Dict[str, Any]], float, Optional[str]]:
    """Run the project's generated suite once. Returns (status_by_test, raw results, seconds, error)."""
    from agents.test_execution.ui_execution.agent import UIExecutionAgent

    started = time.monotonic()
    out = UIExecutionAgent(settings=_settings()).execute({"project_name": project, "headless": True}, {})
    elapsed = round(time.monotonic() - started, 1)
    results = out.get("results") or []
    if out.get("status") == "failed" and not results:
        return {}, [], elapsed, out.get("error") or "execution failed with no results"
    statuses = {_test_id(r): normalize_status(r.get("status")) for r in results}
    return statuses, results, elapsed, None


def test_inventory(project_dir: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Executed tests + whatever links them to requirements (scenario traceability text)."""
    from contracts.artifacts import artifact_path, load_payload

    suite = load_payload("test_suite", os.path.join(project_dir, "test_creation", "test_suite.json"), {}) or {}
    spec_to_sid = {}
    for s in suite.get("specs", []):
        if s.get("file"):
            spec_to_sid[os.path.basename(s["file"])] = s.get("spec_id")
    scen_path = artifact_path(project_dir, "business_scenarios", existing_only=True)
    scenarios = {}
    if scen_path:
        for sc in (load_payload("business_scenarios", scen_path, {}) or {}).get("scenarios", []):
            scenarios[sc.get("scenario_id")] = sc
    trace = _trace_links(project_dir)
    inv = []
    for r in results:
        spec_base = os.path.basename(str(r.get("spec_file", "")))
        sid = spec_to_sid.get(spec_base)
        sc = scenarios.get(sid, {})
        # Phase 1: per-test links from traceability.json (by tc annotation, then spec + title); else the
        # result's own ac annotations; else the scenario's ac_ids (inherited).
        link = trace.get(r.get("tc_id")) or trace.get((spec_base, r.get("test_title")))
        if link:
            ac_ids, ac_link = link
        elif r.get("ac_ids"):
            ac_ids, ac_link = list(r["ac_ids"]), "direct"
        else:
            ac_ids, ac_link = sc.get("ac_ids") or [], ("inherited" if sc.get("ac_ids") else None)
        inv.append({
            "id": _test_id(r), "spec_file": r.get("spec_file"), "title": r.get("test_title"),
            "scenario_id": sid, "ac_ids": ac_ids, "ac_link": ac_link, "tc_id": r.get("tc_id"),
            "text": " ".join(str(x) for x in (sc.get("title"), sc.get("traceability"), r.get("test_title")) if x),
        })
    return inv


def _trace_links(project_dir: str) -> Dict[Any, Tuple[List[str], Optional[str]]]:
    """{tc_id | (spec basename, title): (ac_ids, link)} from test_creation/traceability.json, if present."""
    from contracts.artifacts import load_payload

    path = os.path.join(project_dir, "test_creation", "traceability.json")
    if not os.path.exists(path):
        return {}
    out: Dict[Any, Tuple[List[str], Optional[str]]] = {}
    for tc_id, t in ((load_payload("traceability", path, {}) or {}).get("tests") or {}).items():
        value = (list(t.get("ac_ids") or []), t.get("link"))
        out[tc_id] = value
        out[(os.path.basename(t.get("spec_file") or ""), t.get("test_title"))] = value
    return out


def ac_extraction(app: BenchmarkApp, project_dir: str) -> Optional[Dict[str, Any]]:
    """Phase 1: recall of the pipeline's own requirements.json against the app's hand-labelled acs.yaml."""
    from contracts.artifacts import artifact_path, load_payload
    from tools.benchmark.ac_recall import score_recall
    from tools.benchmark.apps import load_ac_truth

    truth = load_ac_truth(app)
    path = artifact_path(project_dir, "requirements", existing_only=True)
    if not truth or not path:
        return None
    extracted: Dict[str, List[Dict[str, Any]]] = {}
    for req in (load_payload("requirements", path, {}) or {}).get("requirements") or []:
        extracted.setdefault(req.get("module_id"), []).extend(req.get("acceptance_criteria") or [])
    result = score_recall(truth, extracted)
    result.pop("rows", None)
    return result


# ── heal probe ────────────────────────────────────────────────────────────────

def _tree_hashes(project_dir: str) -> Dict[str, str]:
    out = {}
    roots = [os.path.join(project_dir, "test_creation", "test_scripts")]
    files = [os.path.join(project_dir, "test_creation", "locator_map.json")]
    for root in roots:
        for d, _, fs in os.walk(root):
            files += [os.path.join(d, f) for f in fs if f.endswith(".spec.ts")]
    for f in files:
        if os.path.exists(f):
            with open(f, "rb") as fh:
                out[os.path.relpath(f, project_dir)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def heal_probe(app: BenchmarkApp, project: str, bug: str, catchers: List[str], port: int,
               server_log: Optional[str]) -> Dict[str, Any]:
    """Heal a scratch copy of the suite against the buggy app. Wrong heal = a test that
    caught the bug passes after healing while the bug is still on."""
    from agents.test_execution.healing.agent import HealingAgent

    scratch = f"{project}__heal_{bug.lower()}"
    src, dst = os.path.join(PROJECTS_BASE, project), os.path.join(PROJECTS_BASE, scratch)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("reports", "test-results", "*.bak"))
    try:
        with AppServer(app, port, bugs=[bug], log_path=server_log):
            run_suite(scratch)  # fresh failing report for the healer to read
            before = _tree_hashes(dst)
            heal_out = HealingAgent(settings=_settings()).execute({"project_name": scratch}, {})
            after = _tree_hashes(dst)
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            statuses, _, _, err = run_suite(scratch)
        healed_green = [t for t in catchers if statuses.get(t) == "passed"]
        return {
            "bug": bug, "healing_status": heal_out.get("status"), "files_changed": changed,
            "applied": len(changed), "wrong": len(healed_green) if changed else 0,
            "hidden_bug_tests": healed_green, "rerun_error": err,
        }
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def rescore(app: BenchmarkApp, path: str) -> Dict[str, Any]:
    """Recompute metrics + Markdown for a saved result file (no app, no LLM), in place."""
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    saved["metrics"] = score(saved["run"], load_bugs(app), load_acs(app), _pricing())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(saved, f, indent=2)
    md = render_markdown(saved["metrics"], saved.get("meta") or {})
    with open(os.path.splitext(path)[0] + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    return saved


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", required=True, choices=sorted(APPS))
    ap.add_argument("--skip-generate", action="store_true", help="reuse the existing generated suite (no LLM)")
    ap.add_argument("--bugs", default="all", help="comma list of bug ids, or 'all'")
    ap.add_argument("--repeat", type=int, default=2, help="bug-free runs (flakiness)")
    heal = ap.add_mutually_exclusive_group()
    heal.add_argument("--with-healing", dest="healing", action="store_true", default=True)
    heal.add_argument("--no-healing", dest="healing", action="store_false")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--workflow", default="full_workflow")
    ap.add_argument("--generation-timeout", type=int, default=5400)
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "benchmarks", "results"))
    ap.add_argument("--label", default="", help="suffix for the result file name (e.g. 'baseline')")
    ap.add_argument("--rescore", metavar="RESULT_JSON", help="re-score a saved result file and exit")
    args = ap.parse_args(argv)

    app = APPS[args.app]
    if args.rescore:
        saved = rescore(app, args.rescore)
        print(render_markdown(saved["metrics"], saved.get("meta") or {}))
        return 0
    port = args.port or app.default_port
    bugs_truth = load_bugs(app)
    all_ids = [b["id"] for b in bugs_truth]
    selected = all_ids if args.bugs == "all" else [b.strip() for b in args.bugs.split(",") if b.strip()]
    unknown = sorted(set(selected) - set(all_ids))
    if unknown:
        print(f"unknown bug ids: {unknown}", file=sys.stderr)
        return 2

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = f"{date}_{app.name}" + (f"_{args.label}" if args.label else "")
    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(REPO_ROOT, ".aqp_artifacts", "benchmark", stem)
    os.makedirs(work, exist_ok=True)
    usage_log = os.path.join(work, "llm_usage.jsonl")
    if not args.skip_generate and os.path.exists(usage_log):
        os.remove(usage_log)
    os.environ["MTA_LLM_USAGE_LOG"] = usage_log  # in-process healing usage lands in the same log
    server_log = os.path.join(work, "app_server.log")

    t0 = time.monotonic()
    base_url = f"http://127.0.0.1:{port}"
    project_dir = materialize_project(app, PROJECTS_BASE, base_url, clean=not args.skip_generate)
    _log(f"project materialised at {project_dir}")
    notes: List[str] = []
    record: Dict[str, Any] = {"app": app.name, "clean_runs": [], "bug_runs": {}, "bug_run_errors": {},
                              "runtime_s": {"executions": []}}

    gen_rc, gen_s = None, None
    if not args.skip_generate:
        from tools.project_manifest import load_project_manifest

        if (load_project_manifest(app.project_name).get("discovery") or {}).get("deep"):
            record["deep_discovery"] = deep_discovery_pass(app, port, server_log)
            record["runtime_s"]["deep_discovery"] = record["deep_discovery"]["seconds"]
            _log(f"deep discovery: {record['deep_discovery'].get('status')} in {record['deep_discovery']['seconds']}s")
    with AppServer(app, port, log_path=server_log):
        if not args.skip_generate:
            gen_rc, gen_s, disc_s = generate(app.project_name, list(app.module_reqs), usage_log,
                                             args.generation_timeout, args.workflow)
            record["runtime_s"]["discovery_by_module"] = disc_s
            _log(f"generation finished rc={gen_rc} in {gen_s}s")
            bad = {m: c for m, c in gen_rc.items() if c != 0}
            if bad:
                notes.append(f"Generation (main.py --module) exited non-zero for {bad}; scores use whatever specs it produced.")
        record["runtime_s"]["generation"] = gen_s
        last_results: List[Dict[str, Any]] = []
        for i in range(max(1, args.repeat)):
            statuses, results, secs, err = run_suite(app.project_name)
            record["runtime_s"]["executions"].append(secs)
            if err:
                notes.append(f"Bug-free run {i + 1} produced no results: {err}")
            record["clean_runs"].append(statuses)
            last_results = results or last_results
            _log(f"bug-free run {i + 1}: {sum(s == 'passed' for s in statuses.values())}/{len(statuses)} passed")
    record["tests"] = test_inventory(project_dir, last_results)
    record["ac_extraction"] = ac_extraction(app, project_dir)

    if not record["tests"]:
        notes.append("No tests were executed — detection cannot be measured.")
    for bug in selected if record["tests"] else []:
        with AppServer(app, port, bugs=[bug], log_path=server_log):
            statuses, _, secs, err = run_suite(app.project_name)
        record["runtime_s"]["executions"].append(secs)
        if err:
            record["bug_run_errors"][bug] = err
        else:
            record["bug_runs"][bug] = statuses
        _log(f"{bug}: {sum(s == 'failed' for s in statuses.values())} failing")

    from tools.benchmark.score import detect_bugs

    if args.healing and record["bug_runs"]:
        caught = {b: t for b, t in detect_bugs(record["clean_runs"], record["bug_runs"]).items() if t}
        details = []
        for bug, catchers in caught.items():
            _log(f"heal probe {bug} ({len(catchers)} catching test(s))")
            try:
                details.append(heal_probe(app, app.project_name, bug, catchers, port, server_log))
            except Exception as exc:  # a probe failure must not lose the rest of the run
                details.append({"bug": bug, "error": f"{type(exc).__name__}: {exc}", "applied": 0, "wrong": 0})
        record["heals"] = {"applied": sum(d.get("applied", 0) for d in details),
                           "wrong": sum(d.get("wrong", 0) for d in details), "details": details}
        if not caught:
            notes.append("Heal probe not run: no bug was caught, so there was nothing a heal could hide.")
    elif not args.healing:
        notes.append("Heal probe disabled (--no-healing).")

    record["runtime_s"]["total"] = round(time.monotonic() - t0, 1)
    from connectors.llm.usage import summarize_log

    record["llm_usage"] = summarize_log(usage_log)
    if args.skip_generate:
        notes.append("--skip-generate: generation LLM usage/runtime are not part of this run.")

    metrics = score(record, bugs_truth, load_acs(app), _pricing())
    meta = {"date": date, "commit": _commit(), "label": args.label, "app": app.name, "port": port,
            "bugs_selected": selected, "repeat": args.repeat, "healing": args.healing,
            "skip_generate": args.skip_generate, "generation_rc": gen_rc, "notes": notes}
    with open(os.path.join(args.out, f"{stem}.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "metrics": metrics, "run": record}, f, indent=2)
    md = render_markdown(metrics, meta)
    with open(os.path.join(args.out, f"{stem}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print("\n" + md)
    _log(f"results: {os.path.join(args.out, stem)}.json / .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
