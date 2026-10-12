"""
integration.py — Phase 9 in the agent-evaluation DAG (design §7, §14 S9–S11).

Pure functions shared by AgentQualityTestingAgent, the pipeline, brd_compliance, compliance_scoring and the final
report, so those steps only call in here and stay unchanged when a run has no `agent_quality`:

    why = not_applicable(request)                    # None, or the reason the step skips
    agent = resolve_eval_set(github_url)             # eval_sets/index.yaml → agent folder (the per-project opt-in)
    aq = summarize(result, regression, ...)          # the compact `agent_quality` result key
    rows = test_case_rows(result)                    # TestCase rows to APPEND (category "agent_quality")
    gates = quality_gates(aq)                        # gates for compliance_scoring
    xref = cross_reference(aq, criterion_verdicts)   # brd_compliance: eval-set ACs that match run criteria
"""

import os
import re
from typing import Any, Dict, List, Optional

import yaml

from tools.agent_tests.config import SAFETY_DIMENSIONS
from tools.agent_tests.dataset import DATASET_ROOT

INDEX_FILE = "index.yaml"
# app types reachable through a chat / message API (same set the chat/API fallback serves)
_APP_TYPES = {"Chatbot", "REST API", "Hybrid Application", "Unknown", None}
_COMPONENTS = {"Chatbot", "REST API"}
_STATUS = {"pass": "passed", "fail": "failed", "non_deterministic": "failed"}
MAX_EVIDENCE = 25


def normalise_repo_url(url: Optional[str]) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^git@github\.com:", "https://github.com/", u)
    u = re.sub(r"\.git$", "", u.rstrip("/"))
    return re.sub(r"^http://", "https://", u)


def resolve_eval_set(github_url: Optional[str], root: Optional[str] = None) -> Optional[str]:
    """The eval-set folder registered for a repository in eval_sets/index.yaml, or None (Phase 9 off)."""
    path = os.path.join(root or DATASET_ROOT, INDEX_FILE)
    if not github_url or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    want = normalise_repo_url(github_url)
    for entry in data.get("projects") or []:
        if isinstance(entry, dict) and normalise_repo_url(entry.get("github_url")) == want and entry.get("agent"):
            agent = str(entry["agent"])
            return agent if os.path.exists(os.path.join(root or DATASET_ROOT, agent, "agent.yaml")) else None
    return None


def not_applicable(request: Dict[str, Any]) -> Optional[str]:
    if request.get("mode") == "brd_only" or not (request.get("live_url") or "").strip():
        return "the app is not deployed"
    c = request.get("app_classification") or {}
    if c.get("app_type") not in _APP_TYPES and not (_COMPONENTS & set(c.get("components") or [])):
        return f"not a chatbot / agent / API app ({c.get('app_type')})"
    return None


def _evidence(rec: Dict[str, Any]) -> Dict[str, Any]:
    run = next((r for r in rec["runs"] if r["outcome"] in ("fail", "unverified_judge")), rec["runs"][0])
    j = run.get("judge") or {}
    return {
        "case_id": rec["id"], "dimension": rec["dimension"], "title": rec["title"], "ac_ids": rec["ac_ids"],
        "outcome": rec["outcome"], "stats": rec.get("stats"),
        "failed_checks": [c for c in run.get("checks") or [] if c["result"] in ("fail", "unsure")][:6],
        "judge": {k: j.get(k) for k in ("verdict", "reasoning", "verified_quotes", "model")} if j else None,
        "transcript": [{"session": t["session"], "user": t["user"][:600], "reply": t["reply"][:900]}
                       for t in run.get("transcript") or []][:12],
    }


def summarize(result: Dict[str, Any], regression: Optional[Dict[str, Any]], agent: str, spec,
              artifact: Optional[str] = None) -> Dict[str, Any]:
    dims = {}
    for d, v in result["dimensions"].items():
        st = v.get("stats") or {}
        dims[d] = {"outcome": v["outcome"], "verdict": v["verdict"], "pass_rate": st.get("pass_rate"),
                   "ci_low": st.get("ci_low"), "ci_high": st.get("ci_high"), "n": st.get("n"),
                   "cases": v["cases"], "failed_cases": v["failed_cases"],
                   "unverified_judge_runs": v.get("unverified_judge_runs", 0), "reason": st.get("reason"),
                   **({"budget_checks": v["budget_checks"]} if "budget_checks" in v else {})}
    bad = [r for r in result["cases"] if r["outcome"] in ("fail", "non_deterministic", "unverified_judge")]
    bad.sort(key=lambda r: (r["outcome"] == "unverified_judge", r["dimension"] not in SAFETY_DIMENSIONS))
    by_ac: Dict[str, Dict[str, int]] = {}
    for r in result["cases"]:
        for ac in r["ac_ids"]:
            row = by_ac.setdefault(ac, {"cases": 0, "pass": 0, "fail": 0, "undecided": 0})
            row["cases"] += 1
            key = "pass" if r["outcome"] == "pass" else "fail" if r["outcome"] in ("fail", "non_deterministic") \
                else "undecided"
            row[key] += 1
    return {
        "agent": agent, "agent_version": spec.agent_version, "run_id": result["run_id"],
        "judge": result.get("judge"), "requests": result["requests"], "duration_s": result["duration_s"],
        "latency": result["latency"], "dimensions": dims,
        "failed": [_evidence(r) for r in bad[:MAX_EVIDENCE]], "failed_total": len(bad),
        "canary_hits": result["canary_hits"], "by_acceptance_criterion": dict(sorted(by_ac.items())),
        "cut": result["cut"], "unreviewed_cases": result["unreviewed_cases"], "regression": regression,
        "artifact": artifact,
    }


def _why(outcome: str, run: Dict[str, Any]) -> str:
    checks = run.get("checks") or []
    shown = [c for c in checks if c["result"] in ("fail", "unsure")] or [c for c in checks if c["result"] == "not_applicable"]
    detail = "; ".join(f"{c['name']}: {c['detail']}" for c in shown[:3])
    if not detail:
        detail = run.get("error") or ("only the rubric can decide this case" if outcome == "needs_judge" else outcome)
    j = run.get("judge") or {}
    if j.get("reasoning") and outcome in ("unverified_judge", "needs_judge"):
        detail += f"; judge ({j.get('verdict')}, not counted): {j['reasoning']}"
    return f"{outcome}: {detail}"[:1000]


def test_case_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    latency = result["dimensions"].get("latency_cost") or {}
    for r in result["cases"]:
        run = next((x for x in r["runs"] if x["outcome"] != "pass"), r["runs"][0])
        first = (run.get("transcript") or [{}])[0]
        st = r.get("stats") or {}
        j = run.get("judge") or {}
        status = _STATUS.get(r["outcome"], "inconclusive")
        why = None if status == "passed" else _why(r["outcome"], run)
        if r["dimension"] == "latency_cost" and r["outcome"] != "error":  # decided by the run's budgets
            status = _STATUS.get(latency.get("verdict"), "inconclusive")
            failed = [c for c in latency.get("budget_checks") or [] if c["result"] == "fail"]
            why = None if status == "passed" else ("over budget: " + "; ".join(c["detail"] for c in failed))[:1000]
        rows.append({
            "code": r["id"], "title": r["title"], "dimension": r["dimension"], "status": status,
            "criterion_code": (r["ac_ids"] or [None])[0], "input": first.get("user"), "actual": first.get("reply"),
            "expected": r.get("rubric"), "judge_score": j.get("score"), "judge_reasoning": j.get("reasoning"),
            "error_summary": why,
            "duration_ms": int(sum(t.get("latency_ms") or 0 for t in run.get("transcript") or [])),
            "pass_rate": st.get("pass_rate"),
        })
    return rows


def quality_gates(aq: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not aq:
        return []
    dims = aq.get("dimensions") or {}
    gates: List[Dict[str, str]] = []
    safety = [d for d in SAFETY_DIMENSIONS if (dims.get(d) or {}).get("outcome") == "fail"]
    if safety or aq.get("canary_hits"):
        gates.append({"gate": "agent_safety_defect", "level": "block",
                      "reason": "AI agent safety tests failed: " + ", ".join(safety or ["system-prompt canary leaked"])})
    failing = [d for d, v in dims.items() if v.get("verdict") == "fail" and d not in safety]
    if failing:
        gates.append({"gate": "agent_quality_gate", "level": "warn",
                      "reason": "AI agent quality below the statistical gate: " + ", ".join(failing)})
    reg = aq.get("regression") or {}
    if reg and not reg.get("ok", True):
        gates.append({"gate": "agent_regression", "level": "warn",
                      "reason": "Regression against the previous run: " + ", ".join(
                          f"{r['dimension']} ({r.get('delta_points')} pts)" for r in reg.get("regressions") or [])})
    unverified = [d for d, v in dims.items() if v.get("unverified_judge_runs")]
    if unverified:
        gates.append({"gate": "agent_judge_unverified", "level": "warn",
                      "reason": "LLM-judge verdicts not counted (judge not calibrated, Cohen's kappa < 0.6 or no "
                                "labels): " + ", ".join(unverified)})
    return gates


def apply_gates(score: Dict[str, Any], aq: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Score dict with the Phase 9 gates added (the 'all clear' gate removed when a new gate is not a pass)."""
    extra = quality_gates(aq)
    if not extra:
        return score
    gates = [g for g in score.get("gates") or [] if g.get("gate") != "all"] + extra
    return {**score, "gates": gates}


def cross_reference(aq: Optional[Dict[str, Any]], criterion_verdicts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Eval-set AC ids that are also criterion codes of this run, with both verdicts side by side. Never changes a
    criterion verdict: the eval set's AC ids and the run's re-extracted codes can drift (design §14 S10)."""
    if not aq:
        return None
    codes = {v.get("criterion_code") or v.get("code"): v for v in criterion_verdicts or []}
    rows = []
    for ac, counts in (aq.get("by_acceptance_criterion") or {}).items():
        v = codes.get(ac)
        rows.append({"ac_id": ac, **counts, "in_run": v is not None,
                     "run_verdict": (v or {}).get("verdict") or (v or {}).get("resolved_verdict")})
    return {"agent": aq.get("agent"), "matched": sum(1 for r in rows if r["in_run"]), "total": len(rows),
            "criteria": rows,
            "note": "Phase 9 results are reported per eval-set AC id; they do not change the run's criterion verdicts."}
