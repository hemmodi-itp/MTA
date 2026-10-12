"""
score.py — pure benchmark scoring (Phase 0.3). No I/O in `score()`.

Input — a run record (built by tools/benchmark/run.py, or synthetic in tests):

    {
      "app": "buggy_shop",
      "tests": [{"id": "M01/x.spec.ts::title", "spec_file": "...", "title": "...",
                 "scenario_id": "...", "ac_ids": [...], "text": "..."}],
      "clean_runs": [{test_id: "passed"|"failed"|"skipped"}, ...],   # >= 1, all bugs off
      "bug_runs": {"BUG_07": {test_id: status}, ...},                # one bug on at a time
      "bug_run_errors": {"BUG_09": "why the run produced no results"},
      "heals": {"applied": 3, "wrong": 1, "details": [...]},          # optional
      "runtime_s": {"generation": 812.4, "executions": [...], "total": 1503.2},
      "llm_usage": {"gemini/gemini-3.6-flash": {"calls": 40, "cache_hits": 2,
                    "input_tokens": 1, "output_tokens": 2}},
    }

Metric definitions (docs/phases/phase-0-design.md §4.2):
  * caught(bug)  <=> some test PASSED in every clean run and FAILED in that bug's run.
                     A test that fails when bug-free can never count as a catch.
  * detection    = caught / bugs evaluated (bugs whose run produced results).
  * false-failure= tests failing in the first clean run / tests executed there.
  * flaky        = tests whose outcome differs across clean runs / tests in all runs.
  * AC coverage  = ACs linked to >= 1 executed test / all ACs. Link = the test's
                   `ac_ids`, else an exact AC-xx.y id found in its title/text.
  * heal precision = 1 - wrong heals / heals applied (None when no heals).
  * cost         = tokens x pricing; None (and listed) for unpriced models.
"""

import re
import statistics
from typing import Any, Dict, Iterable, List, Optional

PASS = "passed"
FAIL = "failed"
SKIP = "skipped"

_AC_RE = re.compile(r"\bAC-\d+\.\d+\b")
_STATUS_MAP = {
    "passed": PASS, "success": PASS, "expected": PASS, "flaky": PASS, "pass": PASS,
    "failed": FAIL, "failure": FAIL, "unexpected": FAIL, "timedout": FAIL, "timedOut": FAIL,
    "interrupted": FAIL, "error": FAIL, "fail": FAIL,
    "skipped": SKIP, "skip": SKIP,
}


def normalize_status(status: Any) -> str:
    return _STATUS_MAP.get(str(status or "").strip(), FAIL if status else SKIP)


def _executed(run: Dict[str, str]) -> List[str]:
    return [t for t, s in run.items() if normalize_status(s) in (PASS, FAIL)]


def _ratio(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def _ac_root(ac_id: str) -> str:
    """'AC-03.2.1' (an atomic child, Phase 1) counts toward its BRD criterion 'AC-03.2'."""
    m = _AC_RE.match(ac_id)
    return m.group(0) if m else ac_id


def ac_links(test: Dict[str, Any], direct_only: bool = False) -> List[str]:
    """AC ids a test covers: explicit ac_ids (Phase 1 traceability) first, else ids in its text.
    direct_only: only links the generator made for this test (not inherited from its scenario)."""
    if direct_only and test.get("ac_link") not in ("direct", "similarity"):
        return []
    ids = [a for a in (test.get("ac_ids") or []) if isinstance(a, str)]
    if ids:
        return sorted({_ac_root(a) for a in ids})
    if direct_only:
        return []
    text = " ".join(str(test.get(k) or "") for k in ("title", "text", "scenario_title", "traceability"))
    return sorted(set(_AC_RE.findall(text)))


def detect_bugs(clean_runs: List[Dict[str, str]], bug_runs: Dict[str, Dict[str, str]]) -> Dict[str, List[str]]:
    """{bug_id: [test ids that caught it]} — only bugs whose run has results."""
    if not clean_runs:
        return {b: [] for b in bug_runs}
    stable_pass = set.intersection(*[
        {t for t, s in run.items() if normalize_status(s) == PASS} for run in clean_runs
    ])
    return {
        bug: sorted(t for t, s in run.items() if t in stable_pass and normalize_status(s) == FAIL)
        for bug, run in bug_runs.items()
    }


def flaky_tests(clean_runs: List[Dict[str, str]]) -> Optional[List[str]]:
    if len(clean_runs) < 2:
        return None
    common = set.intersection(*[set(r) for r in clean_runs])
    out = []
    for t in sorted(common):
        outcomes = {normalize_status(r[t]) for r in clean_runs} - {SKIP}
        if len(outcomes) > 1:
            out.append(t)
    return out


def llm_cost(usage: Dict[str, Dict[str, int]], pricing: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    total_in = sum(v.get("input_tokens", 0) for v in usage.values())
    total_out = sum(v.get("output_tokens", 0) for v in usage.values())
    calls = sum(v.get("calls", 0) for v in usage.values())
    cache_hits = sum(v.get("cache_hits", 0) for v in usage.values())
    cost = 0.0
    unpriced = []
    for key, v in sorted(usage.items()):
        model = key.split("/", 1)[-1]
        price = pricing.get(model) or pricing.get(key)
        if not price or price.get("input_per_mtok") is None or price.get("output_per_mtok") is None:
            if v.get("input_tokens", 0) or v.get("output_tokens", 0):
                unpriced.append(key)
            continue
        cost += v.get("input_tokens", 0) / 1e6 * float(price["input_per_mtok"])
        cost += v.get("output_tokens", 0) / 1e6 * float(price["output_per_mtok"])
    return {
        "calls": calls, "cache_hits": cache_hits,
        "input_tokens": total_in, "output_tokens": total_out,
        "cost_usd": None if unpriced else round(cost, 4),
        "unpriced_models": unpriced,
    }


def _discovery_metrics(deep: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Phase 2 deep-discovery summary + ground-truth scores (None when the run had no deep pass)."""
    if not deep:
        return None
    keep = ("status", "seconds", "states", "page_templates", "transitions", "forms", "probes", "endpoints",
            "roles", "stopped_by", "error")
    return {**{k: deep.get(k) for k in keep if k in deep}, **(deep.get("metrics") or {})}


def score(run: Dict[str, Any], bugs: Iterable[Dict[str, Any]], acs: Iterable[str],
          pricing: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    bugs = list(bugs)
    acs = sorted(set(acs))
    clean_runs: List[Dict[str, str]] = run.get("clean_runs") or []
    bug_runs: Dict[str, Dict[str, str]] = {b: r for b, r in (run.get("bug_runs") or {}).items() if r}
    tests = {t["id"]: t for t in run.get("tests") or [] if t.get("id")}
    first = clean_runs[0] if clean_runs else {}

    # ── false failures / flakiness ──
    executed = _executed(first)
    failing_clean = sorted(t for t in executed if normalize_status(first[t]) == FAIL)
    flaky = flaky_tests(clean_runs)

    # ── detection ──
    caught_by = detect_bugs(clean_runs, bug_runs)
    truth = {b["id"]: b for b in bugs}
    rows = []
    for bug in bugs:
        bid = bug["id"]
        evaluated = bid in bug_runs
        catchers = caught_by.get(bid, [])
        rows.append({
            "id": bid, "category": bug.get("category"), "severity": bug.get("severity"),
            "affected_ac": bug.get("affected_ac"), "how_detectable": bug.get("how_detectable"),
            "evaluated": evaluated, "caught": bool(catchers) if evaluated else None,
            "caught_by": catchers,
            "note": (run.get("bug_run_errors") or {}).get(bid) if not evaluated else None,
        })
    evaluated_rows = [r for r in rows if r["evaluated"]]
    caught = [r for r in evaluated_rows if r["caught"]]
    by_category: Dict[str, Dict[str, int]] = {}
    for r in evaluated_rows:
        c = by_category.setdefault(r["category"] or "unknown", {"enabled": 0, "caught": 0})
        c["enabled"] += 1
        c["caught"] += 1 if r["caught"] else 0

    # ── AC coverage ──
    covered = set()
    covered_direct = set()
    for tid in executed:
        covered.update(a for a in ac_links(tests.get(tid, {"title": tid})) if a in acs)
        covered_direct.update(a for a in ac_links(tests.get(tid, {"title": tid}), direct_only=True) if a in acs)
    uncovered = [a for a in acs if a not in covered]

    # ── heals ──
    heals = run.get("heals") or {}
    applied = int(heals.get("applied") or 0)
    wrong = int(heals.get("wrong") or 0)

    runtime = run.get("runtime_s") or {}
    durations = [d for d in (runtime.get("executions") or []) if isinstance(d, (int, float))]

    return {
        "app": run.get("app"),
        "ac_extraction_recall": (run.get("ac_extraction") or {}).get("recall"),
        "tests_total": len(tests) or len(first),
        "tests_executed": len(executed),
        "requirement_coverage": {
            "pct": _ratio(len(covered), len(acs)), "covered": sorted(covered),
            "uncovered": uncovered, "total_acs": len(acs),
            # Phase 1: only links made for the test itself (direct / similarity), not inherited from its scenario
            "direct_pct": _ratio(len(covered_direct), len(acs)), "covered_direct": sorted(covered_direct),
            "note": None if covered or not executed else "no executed test links to an AC id (v1 artifacts carry no AC links)",
        },
        "seeded_bug_detection": {
            "rate": _ratio(len(caught), len(evaluated_rows)),
            "caught": len(caught), "evaluated": len(evaluated_rows), "enabled": len(bugs),
            "not_evaluated": [r["id"] for r in rows if not r["evaluated"]],
            "by_category": by_category,
            "bugs": rows,
        },
        "false_failure": {"rate": _ratio(len(failing_clean), len(executed)), "failing_tests": failing_clean},
        "flaky": {"rate": None if flaky is None else _ratio(len(flaky), len(executed)),
                  "tests": flaky, "clean_runs": len(clean_runs)},
        "heal_precision": {"precision": None if not applied else round(1 - wrong / applied, 4),
                           "applied": applied, "wrong": wrong, "measured": bool(heals)},
        "runtime_s": {
            "generation": runtime.get("generation"), "total": runtime.get("total"),
            "execution_median": round(statistics.median(durations), 2) if durations else None,
            "executions": len(durations),
            # Phase 2: the project-level deep pass, and the discovery step of each module run
            "deep_discovery": runtime.get("deep_discovery"),
            "discovery_by_module": runtime.get("discovery_by_module"),
        },
        "discovery": _discovery_metrics(run.get("deep_discovery")),
        "test_design": run.get("test_design"),
        "llm": llm_cost(run.get("llm_usage") or {}, pricing or {}),
        "unknown_bug_ids": sorted(set(bug_runs) - set(truth)),
    }
