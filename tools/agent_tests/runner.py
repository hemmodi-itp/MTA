"""
runner.py — run a golden dataset against an agent: deterministic checks first, an LLM judge only for what they cannot
decide, statistical verdicts per dimension (design D1, §14 S2–S5, S12).

    result = run_suite(spec, cases, transport, tokens, run_id="r1", k=None, judge=judge, workers=6)

Per case, k runs (k=None → each dimension's default: 3, or 5 for safety / consistency). One run = send the input (or
the turns, or the same input N times for consistency) through the conversation transport and apply every assertion
in `expected`. Run outcomes:
  pass | fail | needs_judge (the checks cannot decide) | error (no usable reply)
  unverified_judge (a judge decided, but its dimension is not calibrated — never counted as pass or fail)
With a judge, failures of text-matching checks (judge.escalate) become "unsure" first, then the judge decides every
needs_judge run; canary / schema / trace / latency failures always stand.

Per case: k outcomes → pass / fail / non_deterministic (both seen) / undecided. Robustness variants are compared run
by run with their base case (same verdict → pass). Per dimension two answers:
  outcome  — any defect observed? (fail if any case failed or flipped) — what the benchmark's detection reads
  verdict  — the statistical gate: Wilson lower bound over every decided run (stats.gate); latency_cost uses its
             budgets over every request of the run instead.

Guards: red-team dimensions need agent.yaml authorization (D10); cases that need sessions are cut when the agent has
none; request and time budgets cut cases instead of overrunning, and every cut is listed with a reason.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.agent_tests import checks, stats
from tools.agent_tests.checks import CheckResult, canary, consistency
from tools.agent_tests.checks.latency import budget_checks, percentile
from tools.agent_tests.config import MIN_CASES
from tools.agent_tests.models import DIMENSIONS, RED_TEAM, AgentTestCase, Expected, substitute

OUTCOMES = ("pass", "fail", "needs_judge", "error", "non_deterministic", "unverified_judge")


def requests_needed(case: AgentTestCase) -> int:
    if case.turns:
        return len(case.turns)
    return case.expected.consistent_n or 1


def k_for(spec, case: AgentTestCase, k: Optional[int]) -> int:
    return k if k else spec.repeats_for(case.dimension)


def select(spec, cases: List[AgentTestCase], k: Optional[int], dimensions: Optional[List[str]] = None
           ) -> Tuple[List[AgentTestCase], List[Dict[str, Any]]]:
    """Cases to run (dimension order) and the cut list. Minimums are kept first when the request budget binds."""
    cut: List[Dict[str, Any]] = []
    eligible: List[AgentTestCase] = []
    for c in cases:
        why = None
        if dimensions and c.dimension not in dimensions:
            continue
        if not spec.dimension_enabled(c.dimension):
            why = ("disabled", "dimension disabled in agent.yaml")
        elif c.dimension in RED_TEAM and not spec.authorization.owned_or_authorized:
            why = ("not_authorized", "red-team tests need agent.yaml authorization.owned_or_authorized")
        elif c.turns and not spec.transport.sessions:
            why = ("no_session_support", "multi-turn case, but transport.history is 'none'")
        if why:
            cut.append({"case": c.id, "dimension": c.dimension, "reason": why[0], "detail": why[1]})
        else:
            eligible.append(c)
    eligible.sort(key=lambda c: DIMENSIONS.index(c.dimension))

    def cost(c):
        return requests_needed(c) * k_for(spec, c, k)

    budget = spec.budgets.max_requests
    if sum(cost(c) for c in eligible) <= budget:
        return eligible, cut
    keep, used = set(), 0
    for dim in DIMENSIONS:  # minimums first, dimension by dimension
        for c in [c for c in eligible if c.dimension == dim][:MIN_CASES[dim]]:
            if used + cost(c) <= budget:
                keep.add(c.id)
                used += cost(c)
    for c in eligible:
        if c.id not in keep and used + cost(c) <= budget:
            keep.add(c.id)
            used += cost(c)
    for c in eligible:
        if c.id not in keep:
            cut.append({"case": c.id, "dimension": c.dimension, "reason": "budget",
                        "detail": f"over the request budget ({budget} requests)"})
    return [c for c in eligible if c.id in keep], cut


def _expected(exp: Expected, tokens: Dict[str, str]) -> Expected:
    return Expected.model_validate(substitute(exp.model_dump(exclude_none=True), tokens))


class _Session:
    def __init__(self, transport, history_mode: str, log: List[Dict[str, Any]], threshold: float = 0.8) -> None:
        self.transport, self.mode, self.log, self.threshold = transport, history_mode, log, threshold
        self.histories: Dict[str, List[Dict[str, str]]] = {}

    def send(self, session_id: str, label: str, message: str):
        hist = self.histories.setdefault(session_id, [])
        reply = self.transport.send(session_id, message, list(hist) if self.mode == "client" else [])
        hist += [{"role": "user", "text": message}, {"role": "bot", "text": reply.text}]
        self.log.append({"latency_ms": reply.latency_ms, "tokens": reply.tokens, "ok": reply.ok})
        return reply


def _turn_record(label: str, user: str, reply) -> Dict[str, Any]:
    rec = {"session": label, "user": user[:2000], "reply": reply.text[:4000], "latency_ms": round(reply.latency_ms, 1)}
    if reply.trace is not None:
        rec["trace"] = reply.trace
    if not reply.ok:
        rec["error"] = reply.error
    return rec


def _escalated(results: List[CheckResult], escalate: frozenset) -> List[CheckResult]:
    """Text-matching failures become 'unsure' so the judge decides them (§14 S2)."""
    if not escalate:
        return results
    return [CheckResult(c.name, "unsure", f"escalated to the judge: {c.detail}")
            if c.result == "fail" and c.name.rsplit(".", 1)[-1] in escalate else c for c in results]


def _done(results: List[CheckResult], case: AgentTestCase, transcript, escalate) -> Dict[str, Any]:
    results = _escalated(results, escalate)
    # latency probes are decided by the run-level budgets, never per case and never by a judge
    judgeable = bool(case.rubric) and case.dimension != "latency_cost"
    return {"outcome": checks.outcome_of(results, judgeable), "checks": [c.to_dict() for c in results],
            "transcript": transcript}


def run_case(case: AgentTestCase, session: _Session, tokens: Dict[str, str], run_id: str, rep: int,
             strict_json: bool = True, escalate: frozenset = frozenset()) -> Dict[str, Any]:
    """One run of one case → {outcome, checks, transcript}."""
    base = f"{run_id}:{case.id}:{rep}"
    exp = _expected(case.expected, tokens)
    transcript: List[Dict[str, Any]] = []
    results: List[CheckResult] = []

    if exp.consistent_n:
        text = substitute(case.input, tokens)
        replies = []
        for i in range(exp.consistent_n):
            r = session.send(f"{base}:{i}", "A", text)
            transcript.append(_turn_record(f"#{i + 1}", text, r))
            if not r.ok:
                return {"outcome": "error", "checks": [], "transcript": transcript, "error": r.error}
            replies.append(r.text)
        score = consistency.score(replies, session.threshold)
        results.append(CheckResult("consistency", score.result, score.detail))
        rest = exp.model_copy(update={"consistent_n": None})
        if not rest.is_empty():
            results += checks.evaluate(rest, replies[0], None, tokens, strict_json)
        return _done(results, case, transcript, escalate)

    if case.turns:
        last = None
        planted: Dict[str, set] = {}  # token name -> sessions whose user turns carried it
        for i, turn in enumerate(case.turns):
            text = substitute(turn.user, tokens)
            for name in [n for n in tokens if "{{" + n + "}}" in turn.user]:
                planted.setdefault(name, set()).add(turn.session)
            r = session.send(f"{base}:{turn.session}", turn.session, text)
            transcript.append(_turn_record(turn.session, text, r))
            if not r.ok:
                return {"outcome": "error", "checks": [], "transcript": transcript, "error": r.error}
            if turn.expected:
                for c in checks.evaluate(_expected(turn.expected, tokens), r.text, r.trace, tokens, strict_json):
                    results.append(CheckResult(f"turn{i + 1}.{c.name}", c.result, c.detail))
            last = r
        # canaries: every reply of a session that did not itself receive the token must be clean
        for name in exp.canary_absent or []:
            token = tokens.get(name)
            if not token:
                results.append(CheckResult(f"canary:{name}", "not_applicable", "no such token in this run"))
                continue
            other = [t for t in transcript if t["session"] not in planted.get(name, set())]
            leaks = [(t["session"], v) for t in other if (v := canary.find(t["reply"], token))]
            results.append(CheckResult(f"canary:{name}", "fail" if leaks else "pass",
                                       f"leaked to session {leaks[0][0]} ({', '.join(leaks[0][1])})" if leaks
                                       else f"absent from {len(other)} reply(ies) of other sessions"))
        rest = exp.model_copy(update={"canary_absent": None})
        if not rest.is_empty():
            results += checks.evaluate(rest, last.text, last.trace, tokens, strict_json)
        return _done(results, case, transcript, escalate)

    text = substitute(case.input, tokens)
    r = session.send(f"{base}:A", "A", text)
    transcript.append(_turn_record("A", text, r))
    if not r.ok:
        return {"outcome": "error", "checks": [], "transcript": transcript, "error": r.error}
    return _done(checks.evaluate(exp, r.text, r.trace, tokens, strict_json), case, transcript, escalate)


def combine(outcomes: List[str]) -> str:
    """k run outcomes → one case outcome."""
    decided = [o for o in outcomes if o in ("pass", "fail")]
    if decided:
        if "pass" in decided and "fail" in decided:
            return "non_deterministic"
        return decided[0]
    for o in ("error", "unverified_judge", "needs_judge"):
        if o in outcomes:
            return o
    return outcomes[0] if outcomes else "needs_judge"


def _judge_runs(judge, case: AgentTestCase, runs: List[Dict[str, Any]], tokens: Dict[str, str]) -> None:
    for run in runs:
        if run["outcome"] != "needs_judge":
            continue
        j = judge.judge_run(case, run, tokens)
        run["judge"] = j
        if j.get("verdict") in ("pass", "fail"):
            run["decided_by"] = "judge"
            run["outcome"] = j["verdict"] if judge.verified(case.dimension) else "unverified_judge"


def run_suite(spec, cases: List[AgentTestCase], transport, tokens: Dict[str, str], run_id: str,
              k: Optional[int] = 1, dimensions: Optional[List[str]] = None, strict_json: bool = True,
              emit: Optional[Callable[[str], None]] = None, judge=None, workers: int = 1,
              stop: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    emit = emit or (lambda *_: None)
    started = time.monotonic()
    chosen, cut = select(spec, cases, k, dimensions)
    log: List[Dict[str, Any]] = []
    session = _Session(transport, spec.transport.history, log, spec.thresholds.consistency_similarity)
    deadline = started + spec.budgets.max_minutes * 60
    escalate = frozenset(judge.escalate) if judge is not None else frozenset()
    records: Dict[str, Dict[str, Any]] = {}

    def execute(case: AgentTestCase) -> None:
        if stop is not None and stop():
            cut.append({"case": case.id, "dimension": case.dimension, "reason": "cancelled",
                        "detail": "the run was cancelled"})
            return
        if time.monotonic() > deadline:
            cut.append({"case": case.id, "dimension": case.dimension, "reason": "budget",
                        "detail": f"over the time budget ({spec.budgets.max_minutes} min)"})
            return
        runs = [run_case(case, session, tokens, run_id, rep, strict_json, escalate)
                for rep in range(k_for(spec, case, k))]
        if judge is not None:
            _judge_runs(judge, case, runs, tokens)
        rec = {"id": case.id, "dimension": case.dimension, "title": case.title, "ac_ids": case.ac_ids,
               "source": case.source, "reviewed": case.reviewed, "rubric": case.rubric,
               "outcome": combine([r["outcome"] for r in runs]), "runs": runs}
        records[case.id] = rec
        if rec["outcome"] != "pass":
            emit(f"{case.dimension} {case.id}: {rec['outcome']}")

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(execute, chosen))
    else:
        for case in chosen:
            execute(case)

    by_id = {c.id: c for c in chosen}
    _robustness(chosen, records)
    latencies = [e["latency_ms"] for e in log if e["ok"]]
    tok = [e["tokens"] for e in log if e["ok"] and e["tokens"] is not None]
    lat_checks = budget_checks(latencies, tok, spec.budgets)
    hits = [{"case": rec["id"], "token": name, "variants": variants}
            for rec in records.values() for run in rec["runs"] for t in run["transcript"]
            for name, variants in canary.scan(t["reply"], {n: v for n, v in tokens.items() if n == "CANARY_SYS"}).items()]
    ordered = [records[c.id] for c in chosen if c.id in records]
    dims = {dim: _dimension(spec, dim, [r for r in ordered if r["dimension"] == dim],
                            [c for c in cut if c["dimension"] == dim], lat_checks) for dim in DIMENSIONS}
    for rec in ordered:
        rec["stats"] = stats.case_summary([r["outcome"] for r in rec["runs"]])
    return {
        "run_id": run_id,
        "agent": spec.agent,
        "agent_version": spec.agent_version,
        "agent_model": spec.agent_model,
        "k": k or "per_dimension",
        "judge": {"model": getattr(judge, "model", None), "calibrated": getattr(judge, "calibrated_dimensions", [])}
        if judge is not None else None,
        "transport": getattr(transport, "kind", "unknown"),
        "tokens": tokens,
        "requests": len(log),
        "duration_s": round(time.monotonic() - started, 1),
        "latency": {"p50_ms": percentile(latencies, 50), "p95_ms": percentile(latencies, 95),
                    "p95_tokens_per_turn": percentile(tok, 95), "ttft_note": "time to first token = total time "
                    "(non-streaming transport)"},
        "dimensions": dims,
        "cases": ordered,
        "canary_hits": hits,
        "cut": cut,
        "unreviewed_cases": sum(1 for c in chosen if c.id in records and not by_id[c.id].reviewed),
    }


def _robustness(chosen: List[AgentTestCase], records: Dict[str, Dict[str, Any]]) -> None:
    """A variant run passes when it gets the same verdict as the base case's run with the same index."""
    for case in chosen:
        rec, base_id = records.get(case.id), case.expected.same_as
        if not rec or not base_id or base_id not in records:
            continue
        base_runs = records[base_id]["runs"]
        rec["raw_outcome"] = rec["outcome"]
        for j, run in enumerate(rec["runs"]):
            base = base_runs[j]["outcome"] if j < len(base_runs) else records[base_id]["outcome"]
            raw = run["outcome"]
            run["raw_outcome"] = raw
            if base in ("pass", "fail") and raw in ("pass", "fail"):
                run["outcome"] = "pass" if raw == base else "fail"
            elif raw != "error":
                run["outcome"] = "needs_judge" if "unverified_judge" not in (base, raw) else "unverified_judge"
        rec["outcome"] = combine([r["outcome"] for r in rec["runs"]])
        base_case = records[base_id]["outcome"]
        rec["same_as"] = {"base": base_id, "base_outcome": base_case,
                          "detail": "same verdict as the base case" if rec["outcome"] == "pass" else
                          f"base case {base_case}, this variant {rec['raw_outcome']}"}


def _dimension(spec, dim: str, recs: List[Dict[str, Any]], cuts: List[Dict[str, Any]],
               lat_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {o: sum(1 for r in recs if r["outcome"] == o) for o in OUTCOMES}
    runs = [run for r in recs for run in r["runs"]]
    passes = sum(1 for run in runs if run["outcome"] == "pass")
    fails = sum(1 for run in runs if run["outcome"] == "fail")
    unverified = sum(1 for run in runs if run["outcome"] == "unverified_judge")
    judged = sum(1 for run in runs if run.get("decided_by") == "judge")
    if dim == "latency_cost" and recs:
        decided = [c for c in lat_checks if c["result"] != "not_applicable"]
        outcome = ("fail" if any(c["result"] == "fail" for c in decided) else
                   "error" if counts["error"] == len(recs) else "pass" if decided else "needs_judge")
        verdict = {"verdict": outcome if outcome in ("pass", "fail") else "no_decided_runs",
                   "reason": "budgets over every request of the run"}
    else:
        if not recs:
            outcome = "not_run"
        elif counts["fail"] or counts["non_deterministic"]:
            outcome = "fail"
        elif counts["needs_judge"]:
            outcome = "needs_judge"
        elif counts["unverified_judge"]:
            outcome = "unverified_judge"
        elif counts["error"]:
            outcome = "error"
        else:
            outcome = "pass"
        verdict = stats.gate(passes, fails, spec.gate_for(dim)) if recs else {"verdict": "not_run",
                                                                              "reason": "no case ran"}
        if recs and verdict["verdict"] == "no_decided_runs" and unverified:
            verdict = {**verdict, "verdict": "unverified_judge",
                       "reason": f"{unverified} run(s) decided only by an uncalibrated judge"}
    out = {"outcome": outcome, "verdict": verdict["verdict"], "stats": verdict, "cases": len(recs), **counts,
           "runs": len(runs), "judged_runs": judged, "unverified_judge_runs": unverified,
           "failed_cases": [r["id"] for r in recs if r["outcome"] in ("fail", "non_deterministic")],
           "cut": len(cuts)}
    if dim == "latency_cost":
        out["budget_checks"] = lat_checks
    return out


def pass_rates(result: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Per-dimension pass rate over decided runs (latency: 1/0 from its budgets) — for stability and regression."""
    out: Dict[str, Optional[float]] = {}
    for dim, d in result["dimensions"].items():
        if dim == "latency_cost":
            out[dim] = None if d["verdict"] not in ("pass", "fail") else float(d["verdict"] == "pass")
        else:
            out[dim] = (d.get("stats") or {}).get("pass_rate")
    return out


def raw_pass_rates(result: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Like pass_rates, but runs decided by an UNCALIBRATED judge count with the judge's verdict. For stability
    measurements only — never for a gate (design §14 S4)."""
    out: Dict[str, Optional[float]] = {}
    for dim in result["dimensions"]:
        if dim == "latency_cost":
            out[dim] = pass_rates(result)[dim]
            continue
        p = f = 0
        for rec in result["cases"]:
            if rec["dimension"] != dim:
                continue
            for run in rec["runs"]:
                o = run["outcome"]
                if o == "unverified_judge":
                    o = (run.get("judge") or {}).get("verdict")
                p += o == "pass"
                f += o == "fail"
        out[dim] = round(p / (p + f), 4) if p + f else None
    return out


def verdict_signature(result: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a run that must be identical across repeats with the same seed (timings excluded)."""
    return {
        "dimensions": {d: (v["outcome"], v["verdict"]) for d, v in result["dimensions"].items()},
        "cases": {c["id"]: c["outcome"] for c in result["cases"]},
        "budget_checks": {c["name"]: c["result"] for c in result["dimensions"]["latency_cost"].get("budget_checks", [])},
    }
