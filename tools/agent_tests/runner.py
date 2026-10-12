"""
runner.py — run a golden dataset against an agent and decide each case with the deterministic checks (design D1).

    result = run_suite(spec, cases, transport, tokens=RunTokens.derive(...).as_dict(), run_id="r1", k=1)

Per case (each of k runs): send the input (or the turns, or the same input N times for consistency) through the
conversation transport, then apply every assertion in `expected`. Outcomes:
  pass | fail | needs_judge (only an LLM judge can decide — Phase 9.3) | error (no usable reply)
  non_deterministic (k > 1 and the runs disagree — Phase 9.4 replaces this with Wilson intervals)
Robustness variants are then compared with their base case (same verdict → pass). latency_cost is decided over every
request of the run against the agent's budgets.

Guards: red-team dimensions run only with agent.yaml authorization (D10); cases that need sessions are cut when the
agent has none; the request and time budgets cut cases rather than overrun, and every cut is listed with a reason.
Nothing here calls an LLM.
"""

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.agent_tests import checks
from tools.agent_tests.checks import CheckResult, canary, consistency
from tools.agent_tests.checks.latency import budget_checks, percentile
from tools.agent_tests.config import MIN_CASES
from tools.agent_tests.models import DIMENSIONS, RED_TEAM, AgentTestCase, Expected, substitute

OUTCOMES = ("pass", "fail", "needs_judge", "error", "non_deterministic")


def requests_needed(case: AgentTestCase) -> int:
    if case.turns:
        return len(case.turns)
    return case.expected.consistent_n or 1


def select(spec, cases: List[AgentTestCase], k: int, dimensions: Optional[List[str]] = None
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

    budget = spec.budgets.max_requests
    if sum(requests_needed(c) * k for c in eligible) <= budget:
        return eligible, cut
    keep, used = set(), 0
    for dim in DIMENSIONS:  # minimums first, dimension by dimension
        for c in [c for c in eligible if c.dimension == dim][:MIN_CASES[dim]]:
            if used + requests_needed(c) * k <= budget:
                keep.add(c.id)
                used += requests_needed(c) * k
    for c in eligible:
        if c.id not in keep and used + requests_needed(c) * k <= budget:
            keep.add(c.id)
            used += requests_needed(c) * k
    for c in eligible:
        if c.id not in keep:
            cut.append({"case": c.id, "dimension": c.dimension, "reason": "budget",
                        "detail": f"over the request budget ({budget} requests, k={k})"})
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


def run_case(case: AgentTestCase, session: _Session, tokens: Dict[str, str], run_id: str, rep: int,
             strict_json: bool = True) -> Dict[str, Any]:
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
        return {"outcome": checks.outcome_of(results, bool(case.rubric)), "checks": [c.to_dict() for c in results],
                "transcript": transcript}

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
        absent = exp.canary_absent or []
        for name in absent:
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
        return {"outcome": checks.outcome_of(results, bool(case.rubric)), "checks": [c.to_dict() for c in results],
                "transcript": transcript}

    text = substitute(case.input, tokens)
    r = session.send(f"{base}:A", "A", text)
    transcript.append(_turn_record("A", text, r))
    if not r.ok:
        return {"outcome": "error", "checks": [], "transcript": transcript, "error": r.error}
    results = checks.evaluate(exp, r.text, r.trace, tokens, strict_json)
    return {"outcome": checks.outcome_of(results, bool(case.rubric)), "checks": [c.to_dict() for c in results],
            "transcript": transcript}


def _combine(outcomes: List[str]) -> str:
    if len(set(outcomes)) == 1:
        return outcomes[0]
    if set(outcomes) <= {"pass", "fail"}:
        return "non_deterministic"
    return "error" if "error" in outcomes else "needs_judge"


def run_suite(spec, cases: List[AgentTestCase], transport, tokens: Dict[str, str], run_id: str, k: int = 1,
              dimensions: Optional[List[str]] = None, strict_json: bool = True,
              emit: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    emit = emit or (lambda *_: None)
    started = time.monotonic()
    chosen, cut = select(spec, cases, k, dimensions)
    log: List[Dict[str, Any]] = []
    session = _Session(transport, spec.transport.history, log, spec.thresholds.consistency_similarity)
    deadline = started + spec.budgets.max_minutes * 60
    records: Dict[str, Dict[str, Any]] = {}

    for n, case in enumerate(chosen, 1):
        if time.monotonic() > deadline:
            cut.append({"case": case.id, "dimension": case.dimension, "reason": "budget",
                        "detail": f"over the time budget ({spec.budgets.max_minutes} min)"})
            continue
        runs = [run_case(case, session, tokens, run_id, rep, strict_json) for rep in range(k)]
        outcome = _combine([r["outcome"] for r in runs])
        records[case.id] = {"id": case.id, "dimension": case.dimension, "title": case.title, "ac_ids": case.ac_ids,
                            "source": case.source, "reviewed": case.reviewed, "rubric": case.rubric,
                            "outcome": outcome, "runs": runs}
        if outcome != "pass":
            emit(f"[{n}/{len(chosen)}] {case.dimension} {case.id}: {outcome}")

    # robustness: a variant passes when it gets the same verdict as its base case
    for case in chosen:
        rec, base_id = records.get(case.id), case.expected.same_as
        if not rec or not base_id or base_id not in records:
            continue
        base, raw = records[base_id]["outcome"], rec["outcome"]
        rec["raw_outcome"] = raw
        if base in ("pass", "fail") and raw in ("pass", "fail"):
            rec["outcome"] = "pass" if raw == base else "fail"
            rec["same_as"] = {"base": base_id, "base_outcome": base,
                              "detail": "same verdict as the base case" if raw == base else
                              f"base case {base}ed, this variant {raw}ed"}
        elif raw != "error":
            rec["outcome"] = "needs_judge"
            rec["same_as"] = {"base": base_id, "base_outcome": base, "detail": "base or variant undecided"}

    latencies = [e["latency_ms"] for e in log if e["ok"]]
    tok = [e["tokens"] for e in log if e["ok"] and e["tokens"] is not None]
    lat_checks = budget_checks(latencies, tok, spec.budgets)
    hits = []
    for rec in records.values():
        for run in rec["runs"]:
            for t in run["transcript"]:
                for name, variants in canary.scan(t["reply"], {k_: v for k_, v in tokens.items()
                                                               if k_ in ("CANARY_SYS",)}).items():
                    hits.append({"case": rec["id"], "token": name, "variants": variants})

    dims: Dict[str, Dict[str, Any]] = {}
    for dim in DIMENSIONS:
        recs = [r for r in records.values() if r["dimension"] == dim]
        counts = {o: sum(1 for r in recs if r["outcome"] == o) for o in OUTCOMES}
        cuts = [c for c in cut if c["dimension"] == dim]
        if dim == "latency_cost" and recs:
            decided = [c for c in lat_checks if c["result"] != "not_applicable"]
            outcome = ("fail" if any(c["result"] == "fail" for c in decided) else
                       "error" if counts["error"] == len(recs) else "pass" if decided else "needs_judge")
        elif not recs:
            outcome = "not_run"
        elif counts["fail"] or counts["non_deterministic"]:
            outcome = "fail"
        elif counts["needs_judge"]:
            outcome = "needs_judge"
        elif counts["error"]:
            outcome = "error"
        else:
            outcome = "pass"
        dims[dim] = {"outcome": outcome, "cases": len(recs), **counts,
                     "failed_cases": [r["id"] for r in recs if r["outcome"] in ("fail", "non_deterministic")],
                     "cut": len(cuts)}
        if dim == "latency_cost":
            dims[dim]["budget_checks"] = lat_checks

    return {
        "run_id": run_id,
        "agent": spec.agent,
        "agent_version": spec.agent_version,
        "k": k,
        "transport": getattr(transport, "kind", "unknown"),
        "tokens": tokens,
        "requests": len(log),
        "duration_s": round(time.monotonic() - started, 1),
        "latency": {"p50_ms": percentile(latencies, 50), "p95_ms": percentile(latencies, 95),
                    "p95_tokens_per_turn": percentile(tok, 95), "ttft_note": "time to first token = total time "
                    "(non-streaming transport)"},
        "dimensions": dims,
        "cases": [records[c.id] for c in chosen if c.id in records],
        "canary_hits": hits,
        "cut": cut,
        "unreviewed_cases": sum(1 for c in chosen if not c.reviewed),
    }


def verdict_signature(result: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a run that must be identical across repeats with the same seed (timings excluded)."""
    return {
        "dimensions": {d: v["outcome"] for d, v in result["dimensions"].items()},
        "cases": {c["id"]: c["outcome"] for c in result["cases"]},
        "budget_checks": {c["name"]: c["result"] for c in result["dimensions"]["latency_cost"].get("budget_checks", [])},
    }
