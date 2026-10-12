"""
bench.py — the buggy_bot benchmark for Phase 9 (acceptance criteria 1-3).

    python -m tools.agent_tests bench --seed 7                 # bot in a subprocess, real HTTP (default)
    python -m tools.agent_tests bench --seed 7 --in-process    # in-process ASGI, fast (unit tests)

Configurations: every flag off (false-positive check), then each weakness alone. A weakness is DETECTED when at
least one dimension in its `detected_by` fails; a failure in a dimension outside `detected_by ∪ may_affect` is a
COLLATERAL false positive. With --repeat 2 every configuration runs twice and the verdicts (timings excluded) must be
identical — same seed, mock mode.

Real-LLM mode (`--llm`, design §14): the bot answers with an LLM (BOT_MODE=llm, model --bot-model, default
gemini-3.5-flash-lite, uncached) and a DIFFERENT judge model (agent.yaml judge, default gemini-3.6-flash) decides the
runs the deterministic checks cannot. Each case runs k times (per-dimension defaults), the baseline is repeated
--repeat times to measure pass-rate variance (AC 3), and detection is reported twice: counting only verified
verdicts (deterministic + calibrated judge) and also counting uncalibrated-judge verdicts. BOT_BUG_10 runs on the
latency dimension only, with a slow-down sized to the LLM budgets.

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
_BOT_KEYS = ("BOT_BUGS", "BOT_CANARY", "BOT_SEED", "BOT_MODE", "BOT_MEMORY_TURNS", "BOT_SLOW_MS", "BOT_TRACES",
             "BOT_LLM_MODEL", "BOT_LLM_CONNECTOR")
BOT_MODEL = "gemini-3.5-flash-lite"
# real-LLM replies take ~1 s and are longer than the mock's: budgets for the llm benchmark (mock keeps agent.yaml's)
LLM_BUDGETS = {"p50_ms": 4000, "p95_ms": 10000, "max_tokens_per_turn_p95": 2000, "max_requests": 4000,
               "max_minutes": 90}
LLM_SLOW_MS = 12000


def load_weaknesses(path: str = WEAKNESSES_YAML) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("weaknesses") or []


def bot_env(flags: List[str], canary: Optional[str], seed: int, base: Optional[dict] = None,
            mode: str = "mock", model: Optional[str] = None, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The bot's environment: every BOT_* knob cleared first, so a flag left in the shell never leaks in."""
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key in _BOT_KEYS or key.startswith("BOT_BUG_"):
            env.pop(key)
    env.update({f: "1" for f in flags})
    env.update({"BOT_SEED": str(seed), "BOT_MODE": mode})
    if mode == "llm":
        env.update({"BOT_LLM_CONNECTOR": "gemini", "BOT_LLM_MODEL": model or BOT_MODEL})
    if canary:
        env["BOT_CANARY"] = canary
    env.update(extra or {})
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
               dimensions: Optional[List[str]] = None, emit=None, mode: str = "mock", judge=None,
               k: Optional[int] = 1, workers: int = 1, bot_model: Optional[str] = None,
               bot_extra: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    run_id = f"bench-{seed}"
    tokens = RunTokens.derive(seed, run_id, system_canary_applicable=spec.canaries.system_prompt_applicable,
                              system_canary=spec.canaries.system_prompt_value).as_dict()
    env = bot_env(flags, tokens.get("CANARY_SYS"), seed, mode=mode, model=bot_model, extra=bot_extra)
    kw = dict(dimensions=dimensions, emit=emit, judge=judge, k=k, workers=workers)
    if in_process:
        with _patched_environ(env):
            from benchmarks.agents.buggy_bot.app import Bot, create_app
            transport = AsgiTransport(create_app(Bot()), spec.transport)
            return run_suite(spec, cases, transport, tokens, run_id, **kw)
    with bot_server(env) as url, _patched_environ({**os.environ, "AQP_ALLOW_PRIVATE_TARGETS": "1"}):
        return run_suite(spec, cases, HttpTransport(url, spec.transport), tokens, run_id, **kw)


def failing(result: Dict[str, Any], include_unverified: bool = False) -> List[str]:
    """Dimensions that observed a defect; with include_unverified, also those an uncalibrated judge failed."""
    out = [d for d, v in result["dimensions"].items() if v["outcome"] == "fail"]
    if include_unverified:
        for rec in result["cases"]:
            if rec["dimension"] not in out and any(run["outcome"] == "unverified_judge"
                                                   and (run.get("judge") or {}).get("verdict") == "fail"
                                                   for run in rec["runs"]):
                out.append(rec["dimension"])
    return [d for d in DIMENSIONS if d in out]


def score(baseline: Dict[str, Any], per_flag: Dict[str, Dict[str, Any]], weaknesses: List[Dict[str, Any]],
          include_unverified: bool = False) -> Dict[str, Any]:
    rows = []
    for w in weaknesses:
        res = per_flag.get(w["id"])
        if res is None:
            continue
        fails = failing(res, include_unverified)
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
    base_fail = failing(baseline, include_unverified)
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
    def evidence(c):  # ≤ 2 non-passing runs; failures and judge "fail" verdicts first, so re-scoring stays exact
        bad = [r for r in c["runs"] if r["outcome"] != "pass"]
        bad.sort(key=lambda r: (r["outcome"] != "fail", (r.get("judge") or {}).get("verdict") != "fail"))
        return bad[:2] or c["runs"][:1]
    out["cases"] = [{**c, "runs": evidence(c)} for c in result["cases"] if c["outcome"] != "pass"]
    out["compact"] = 2
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


def write_report(report: Dict[str, Any], out_dir: str = RESULTS_DIR, label: str = "phase9",
                 md: Optional[str] = None) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f"{report['date']}_buggy_bot_{label}")
    with open(stem + ".json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=1, ensure_ascii=False, sort_keys=True)
    with open(stem + ".md", "w", encoding="utf-8", newline="\n") as f:
        f.write(md if md is not None else markdown(report))
    return [stem + ".json", stem + ".md"]


# ── real-LLM benchmark (design §14) ──────────────────────────────────────────

def run_bench_llm(seed: int = 7, only: Optional[List[str]] = None, repeat: int = 3, bot_model: str = BOT_MODEL,
                  workers: int = 6, k: Optional[int] = None, root: Optional[str] = None, emit=print,
                  judge=None) -> Dict[str, Any]:
    from tools.agent_tests import stats
    from tools.agent_tests.runner import pass_rates, raw_pass_rates
    from tools.agent_tests.spec import Budgets

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(REPO_ROOT, ".env"))  # GOOGLE_API_KEY for the judge and the bot subprocess
    except ImportError:
        pass
    os.environ.setdefault("AQP_LLM_RPM", "300")
    os.environ.setdefault("AQP_LLM_CONCURRENCY", "12")
    directory = agent_dir(AGENT, root)
    base_spec = spec_for(directory)
    spec = base_spec.model_copy(update={"agent_model": bot_model,
                                        "budgets": Budgets(**LLM_BUDGETS, ac_ids=base_spec.budgets.ac_ids)})
    cases, rep = load_cases(directory)
    if rep.errors:
        raise ValueError("eval_sets/buggy_bot has errors: " + "; ".join(rep.errors[:3]))
    if judge is None:
        from tools.agent_tests.calibration import Calibration
        from tools.agent_tests.judge import Judge
        from tools.agent_tests.llm import make_llm
        judge = Judge(make_llm(spec.judge.connector, spec.judge.model), Calibration.load(directory),
                      agent_model=bot_model, escalate=spec.judge.escalate)
    extra = {"AQP_LLM_RPM": os.environ["AQP_LLM_RPM"], "AQP_LLM_CONCURRENCY": os.environ["AQP_LLM_CONCURRENCY"]}
    kw = dict(mode="llm", judge=judge, k=k, workers=workers, bot_model=bot_model)

    def one(name: str, flags: List[str], dimensions: Optional[List[str]] = None,
            more_env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        t0 = time.monotonic()
        res = run_config(spec, cases, flags, seed, False, dimensions=dimensions,
                         bot_extra={**extra, **(more_env or {})}, **kw)
        emit(f"{name:<11} failing {failing(res) or '-'} · incl. unverified judge {failing(res, True) or '-'} "
             f"({res['requests']} requests, {time.monotonic() - t0:.0f}s, judge calls so far {judge.calls})")
        return res

    baselines = [one(f"baseline#{i + 1}", []) for i in range(repeat)]
    weaknesses = [w for w in load_weaknesses() if not only or w["id"] in only]
    per_flag: Dict[str, Dict[str, Any]] = {}
    for w in weaknesses:
        if w["id"] == "BOT_BUG_10":
            per_flag[w["id"]] = one(w["id"], [w["flag"]], ["latency_cost"], {"BOT_SLOW_MS": str(LLM_SLOW_MS)})
        else:
            per_flag[w["id"]] = one(w["id"], [w["flag"]])
    dims = list(DIMENSIONS)
    rates = {d: [pass_rates(r)[d] for r in baselines] for d in dims}
    raw = {d: [raw_pass_rates(r)[d] for r in baselines] for d in dims}
    summary = {
        "verified": score(baselines[0], per_flag, weaknesses, include_unverified=False),
        "including_unverified_judge": score(baselines[0], per_flag, weaknesses, include_unverified=True),
        "stability_verified": stats.stability(rates, spec.stability.max_pass_rate_variance),
        "stability_including_unverified_judge": stats.stability(raw, spec.stability.max_pass_rate_variance),
        "repeat": repeat,
    }

    def dim_row(r: Dict[str, Any], d: str) -> Dict[str, Any]:
        x, st = r["dimensions"][d], r["dimensions"][d].get("stats") or {}
        return {"outcome": x["outcome"], "verdict": x["verdict"], "pass_rate": st.get("pass_rate"),
                "ci_low": st.get("ci_low"), "ci_high": st.get("ci_high"), "n": st.get("n"),
                "unverified_judge_runs": x["unverified_judge_runs"], "raw_pass_rate": raw_pass_rates(r)[d]}

    return {
        "agent": AGENT, "seed": seed, "mode": "llm", "transport": "http", "date": _dt.date.today().isoformat(),
        "bot_model": bot_model, "judge_model": judge.model, "judge_calls": judge.calls,
        "calibrated_dimensions": judge.calibrated_dimensions, "k": k or "per_dimension", "budgets": LLM_BUDGETS,
        "dataset": _manifest(directory), "summary": summary,
        "baseline": [{d: dim_row(r, d) for d in dims} for r in baselines],
        "per_weakness": {name: _dims(v) for name, v in per_flag.items()},
        "latency": {"baseline": baselines[0]["latency"], **{name: v["latency"] for name, v in per_flag.items()}},
        "requests": sum(r["requests"] for r in baselines) + sum(r["requests"] for r in per_flag.values()),
        "runs": {**{f"baseline#{i + 1}": compact(r) for i, r in enumerate(baselines)},
                 **{name: compact(v) for name, v in per_flag.items()}},
    }


def _ok(flag: Optional[bool]) -> str:
    return "n/a" if flag is None else "ok" if flag else "EXCEEDED"


def markdown_llm(report: Dict[str, Any]) -> str:
    s = report["summary"]
    v, u = s["verified"], s["including_unverified_judge"]
    sv, su = s["stability_verified"], s["stability_including_unverified_judge"]
    first = report["baseline"][0]
    cal = ", ".join(report["calibrated_dimensions"]) or "none"
    lines = [
        f"# Phase 9 benchmark — buggy_bot, real LLM ({report['date']})", "",
        f"Bot `{report['bot_model']}` · judge `{report['judge_model']}` ({report['judge_calls']} judge calls; "
        f"calibrated dimensions: {cal}) · k {report['k']} · baseline ×{s['repeat']} · {report['requests']} bot requests",
        "",
        "| Metric | Verified verdicts only | Incl. uncalibrated judge |", "|---|---|---|",
        f"| Seeded weaknesses detected | **{v['detected']} / {v['total']}** | {u['detected']} / {u['total']} |",
        f"| Dimensions failing with all flags off | {len(v['baseline_false_positives'])} "
        f"{v['baseline_false_positives'] or ''} | {len(u['baseline_false_positives'])} "
        f"{u['baseline_false_positives'] or ''} |",
        f"| Collateral failures | {v['collateral_false_positives']} | {u['collateral_false_positives']} |",
        f"| Max pass-rate variance across baseline repeats (limit {sv['max_variance']}) | {sv['worst']} ({_ok(sv['ok'])})"
        f" | {su['worst']} ({_ok(su['ok'])}) |",
        "", "## Baseline (all flags off), run 1", "",
        "| Dimension | Defects | Gate verdict | Pass rate | 95% CI | n | Unverified-judge runs | Raw pass rate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d, x in first.items():
        ci = f"{x['ci_low']}–{x['ci_high']}" if x["ci_low"] is not None else "—"
        lines.append(f"| {d} | {x['outcome']} | {x['verdict']} | {x['pass_rate']} | {ci} | {x['n']} | "
                     f"{x['unverified_judge_runs']} | {x['raw_pass_rate']} |")
    lines += ["", "## Pass-rate variance across baseline repeats", "",
              "| Dimension | Verified rates | Variance | Raw rates | Raw variance |", "|---|---|---|---|---|"]
    for d in first:
        a, b = sv["dimensions"][d], su["dimensions"][d]
        lines.append(f"| {d} | {a['rates']} | {a['variance']} | {b['rates']} | {b['variance']} |")
    lines += ["", "## Detection per weakness", "",
              "| Weakness | Detected (verified) | Detected (incl. unverified judge) | Failing (verified) | "
              "Collateral (incl. unverified) |", "|---|---|---|---|---|"]
    rows_u = {r["id"]: r for r in u["weaknesses"]}
    for r in v["weaknesses"]:
        ru = rows_u[r["id"]]
        lines.append(f"| {r['id']} {r['category']} | {', '.join(r['detected_in']) or '—'} | "
                     f"{', '.join(ru['detected_in']) or '—'} | {', '.join(r['failing_dimensions']) or '—'} | "
                     f"{', '.join(ru['collateral']) or '—'} |")
    return "\n".join(lines) + "\n"


def rescore_llm(report: Dict[str, Any]) -> Dict[str, Any]:
    """Score a saved real-LLM report again against the CURRENT weaknesses.yaml (no new LLM calls)."""
    runs = report["runs"]
    baseline = runs["baseline#1"]
    per_flag = {k: v for k, v in runs.items() if not k.startswith("baseline#")}
    weaknesses = [w for w in load_weaknesses() if w["id"] in per_flag]
    summary = dict(report["summary"])
    summary["verified"] = score(baseline, per_flag, weaknesses, include_unverified=False)  # dimension outcomes: exact
    if all(r.get("compact") == 2 for r in runs.values()):  # judge-fail evidence kept: exact too
        summary["including_unverified_judge"] = score(baseline, per_flag, weaknesses, include_unverified=True)
    return {**report, "summary": summary, "rescored": True}
