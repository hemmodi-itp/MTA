"""
bench.py — the buggy_bot benchmark for Phase 9 (acceptance criteria 1-3).

    python -m tools.agent_tests bench --seed 7                 # bot in a subprocess, real HTTP (default)
    python -m tools.agent_tests bench --seed 7 --in-process    # in-process ASGI, fast (unit tests)

Configurations: every flag off (false-positive check), then each weakness alone. A weakness is DETECTED when at
least one dimension in its `detected_by` fails; a failure in a dimension outside `detected_by ∪ may_affect` is a
COLLATERAL false positive. With --repeat 2 every configuration runs twice and the verdicts (timings excluded) must be
identical — same seed, mock mode.

The bot is MTA-owned and local, so the benchmark plants the run's system-prompt canary through BOT_CANARY and, for
HTTP mode only, sets AQP_ALLOW_PRIVATE_TARGETS=1 for its own process (the documented local-development switch of
tools/agent_eval/net_guard); every request still goes through the guarded opener.
"""

import contextlib
import datetime as _dt
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, Iterator, List, Optional

import yaml

from tools.agent_tests.canaries import RunTokens
from tools.agent_tests.dataset import REPO_ROOT, agent_dir, load_cases, spec_for
from tools.agent_tests.models import DIMENSIONS
from tools.agent_tests.runner import run_suite, verdict_signature
from tools.agent_tests.transport import AsgiTransport, HttpTransport

AGENT = "buggy_bot"
BOT_MODULE = "benchmarks.agents.buggy_bot"
WEAKNESSES_YAML = os.path.join(REPO_ROOT, "benchmarks", "agents", "buggy_bot", "weaknesses.yaml")
RESULTS_DIR = os.path.join(REPO_ROOT, "benchmarks", "results")
_BOT_KEYS = ("BOT_BUGS", "BOT_CANARY", "BOT_SEED", "BOT_MODE", "BOT_MEMORY_TURNS", "BOT_SLOW_MS", "BOT_TRACES")


def load_weaknesses(path: str = WEAKNESSES_YAML) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("weaknesses") or []


def bot_env(flags: List[str], canary: Optional[str], seed: int, base: Optional[dict] = None) -> Dict[str, str]:
    """The bot's environment: every BOT_* knob cleared first, so a flag left in the shell never leaks in."""
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key in _BOT_KEYS or key.startswith("BOT_BUG_"):
            env.pop(key)
    env.update({f: "1" for f in flags})
    env.update({"BOT_SEED": str(seed), "BOT_MODE": "mock"})
    if canary:
        env["BOT_CANARY"] = canary
    return env


@contextlib.contextmanager
def _patched_environ(env: Dict[str, str]) -> Iterator[None]:
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def bot_server(env: Dict[str, str], timeout_s: float = 30.0) -> Iterator[str]:
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", BOT_MODULE, "--port", str(port)], cwd=REPO_ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + timeout_s
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"buggy_bot exited during startup (code {proc.returncode})")
            try:
                with urllib.request.urlopen(url + "/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"buggy_bot not healthy on {url} after {timeout_s}s")
            time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_config(spec, cases, flags: List[str], seed: int, in_process: bool,
               dimensions: Optional[List[str]] = None, emit=None) -> Dict[str, Any]:
    run_id = f"bench-{seed}"
    tokens = RunTokens.derive(seed, run_id, system_canary_applicable=spec.canaries.system_prompt_applicable,
                              system_canary=spec.canaries.system_prompt_value).as_dict()
    env = bot_env(flags, tokens.get("CANARY_SYS"), seed)
    if in_process:
        with _patched_environ(env):
            from benchmarks.agents.buggy_bot.app import Bot, create_app
            transport = AsgiTransport(create_app(Bot()), spec.transport)
            return run_suite(spec, cases, transport, tokens, run_id, dimensions=dimensions, emit=emit)
    with bot_server(env) as url, _patched_environ({**os.environ, "AQP_ALLOW_PRIVATE_TARGETS": "1"}):
        return run_suite(spec, cases, HttpTransport(url, spec.transport), tokens, run_id,
                         dimensions=dimensions, emit=emit)


def failing(result: Dict[str, Any]) -> List[str]:
    return [d for d, v in result["dimensions"].items() if v["outcome"] == "fail"]


def score(baseline: Dict[str, Any], per_flag: Dict[str, Dict[str, Any]], weaknesses: List[Dict[str, Any]]
          ) -> Dict[str, Any]:
    rows = []
    for w in weaknesses:
        res = per_flag.get(w["id"])
        if res is None:
            continue
        fails = failing(res)
        detected_by, allowed = set(w["detected_by"]), set(w["detected_by"]) | set(w.get("may_affect") or [])
        hit = sorted(set(fails) & detected_by)
        evidence = [c for d in hit for c in res["dimensions"][d]["failed_cases"]][:5]
        if "latency_cost" in hit:  # a run-level budget, not a failing case
            evidence += [f"{c['name']} {c['value']} > {c['budget']}"
                         for c in res["dimensions"]["latency_cost"]["budget_checks"] if c["result"] == "fail"]
        rows.append({
            "id": w["id"], "category": w["category"], "severity": w["severity"],
            "detected": bool(hit), "detected_in": hit,
            "failing_dimensions": fails,
            "collateral": sorted(set(fails) - allowed),
            "evidence": evidence,
        })
    base_fail = failing(baseline)
    undecided = [d for d, v in baseline["dimensions"].items() if v["outcome"] in ("needs_judge", "error", "not_run")]
    return {
        "weaknesses": rows,
        "detected": sum(1 for r in rows if r["detected"]),
        "total": len(rows),
        "baseline_false_positives": base_fail,
        "baseline_undecided": undecided,
        "collateral_false_positives": sum(len(r["collateral"]) for r in rows),
    }


def run_bench(seed: int = 7, in_process: bool = False, only: Optional[List[str]] = None, repeat: int = 1,
              root: Optional[str] = None, emit=print) -> Dict[str, Any]:
    directory = agent_dir(AGENT, root)
    spec = spec_for(directory)
    cases, rep = load_cases(directory)
    if rep.errors:
        raise ValueError("eval_sets/buggy_bot has errors: " + "; ".join(rep.errors[:3]))
    weaknesses = [w for w in load_weaknesses() if not only or w["id"] in only]
    configs = [("baseline", [])] + [(w["id"], [w["flag"]]) for w in weaknesses]
    runs: Dict[str, List[Dict[str, Any]]] = {}
    for name, flags in configs:
        for i in range(repeat):
            t0 = time.monotonic()
            res = run_config(spec, cases, flags, seed, in_process)
            runs.setdefault(name, []).append(res)
            emit(f"{name:<11} run {i + 1}/{repeat}: failing {failing(res) or '-'} "
                 f"({res['requests']} requests, {time.monotonic() - t0:.1f}s)")
    firsts = {k: v[0] for k, v in runs.items()}
    summary = score(firsts["baseline"], {k: v for k, v in firsts.items() if k != "baseline"}, weaknesses)
    summary["deterministic"] = all(verdict_signature(r) == verdict_signature(v[0]) for v in runs.values() for r in v)
    summary["repeat"] = repeat
    return {
        "agent": AGENT, "seed": seed, "mode": "mock", "transport": "asgi" if in_process else "http",
        "date": _dt.date.today().isoformat(), "dataset": _manifest(directory),
        "summary": summary,
        "baseline": _dims(firsts["baseline"]),
        "per_weakness": {k: _dims(v) for k, v in firsts.items() if k != "baseline"},
        "latency": {k: v["latency"] for k, v in firsts.items()},
        "runs": {k: compact(v) for k, v in firsts.items()},
    }


def compact(result: Dict[str, Any]) -> Dict[str, Any]:
    """A run without the transcripts of passing cases (the evidence that matters is in the failures)."""
    out = {k: v for k, v in result.items() if k != "cases"}
    out["cases"] = [c for c in result["cases"] if c["outcome"] != "pass"]
    out["passed_cases"] = sum(1 for c in result["cases"] if c["outcome"] == "pass")
    return out


def _dims(result: Dict[str, Any]) -> Dict[str, str]:
    return {d: result["dimensions"][d]["outcome"] for d in DIMENSIONS}


def _manifest(directory: str) -> Dict[str, Any]:
    path = os.path.join(directory, "manifest.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    return {k: m.get(k) for k in ("dataset_version", "generator_version", "catalog_versions", "total", "unreviewed")}


def markdown(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Phase 9 benchmark — buggy_bot ({report['date']})", "",
        f"Seed {report['seed']} · mock mode · transport {report['transport']} · dataset v"
        f"{report['dataset'].get('dataset_version')} ({report['dataset'].get('total')} cases, "
        f"{report['dataset'].get('unreviewed')} unreviewed)", "",
        "| Metric | Value |", "|---|---|",
        f"| Seeded weaknesses detected | **{s['detected']} / {s['total']}** |",
        f"| False positives, all flags off | {len(s['baseline_false_positives'])} "
        f"{s['baseline_false_positives'] or ''} |",
        f"| Undecided dimensions, all flags off | {s['baseline_undecided'] or 'none'} |",
        f"| Collateral false positives (outside detected_by ∪ may_affect) | {s['collateral_false_positives']} |",
        f"| Identical verdicts across {s['repeat']} run(s) per configuration | {'yes' if s['deterministic'] else 'NO'} |",
        "", "| Weakness | Category | Detected in | Other failing dimensions | Collateral | Evidence (cases) |",
        "|---|---|---|---|---|---|",
    ]
    for r in s["weaknesses"]:
        others = [d for d in r["failing_dimensions"] if d not in r["detected_in"]]
        lines.append(f"| {r['id']} | {r['category']} | {', '.join(r['detected_in']) or '**not detected**'} | "
                     f"{', '.join(others) or '—'} | {', '.join(r['collateral']) or '—'} | "
                     f"{', '.join(r['evidence'][:3])} |")
    lines += ["", "## Per-dimension outcome, all flags off", "", "| Dimension | Outcome |", "|---|---|"]
    lines += [f"| {d} | {o} |" for d, o in report["baseline"].items()]
    lat = report["latency"]["baseline"]
    lines += ["", f"Baseline latency p50 {lat['p50_ms']:.1f} ms · p95 {lat['p95_ms']:.1f} ms · "
                  f"p95 tokens/turn {lat['p95_tokens_per_turn']}"]
    return "\n".join(lines) + "\n"


def write_report(report: Dict[str, Any], out_dir: str = RESULTS_DIR, label: str = "phase9") -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f"{report['date']}_buggy_bot_{label}")
    with open(stem + ".json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=1, ensure_ascii=False, sort_keys=True)
    with open(stem + ".md", "w", encoding="utf-8", newline="\n") as f:
        f.write(markdown(report))
    return [stem + ".json", stem + ".md"]
