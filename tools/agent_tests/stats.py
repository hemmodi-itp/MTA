"""
stats.py — statistical verdicts for non-deterministic agents (Phase 9.4, design §14 S5/S6).

    wilson(28, 30)                         -> (0.787, 0.982)     95 % Wilson score interval
    gate(passes=28, fails=2, gate=GateCfg(min_lower_bound=0.75)) -> {"verdict": "pass", ...}

Each case runs k times; every decided run (pass or fail — deterministic, or judged by a calibrated judge) is one
Bernoulli trial of the dimension. The verdict gates on the LOWER bound of the interval, so a dimension passes only
when the evidence says its pass rate is high, not when it merely looked high on a few runs. When even a perfect
result could not reach the bound (too few runs), the verdict is "insufficient_samples" — never a silent pass.
"""

import math
from statistics import pvariance
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.agent_tests.config import WILSON_Z


def wilson(successes: int, n: int, z: float = WILSON_Z) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion; (0, 1) when n == 0."""
    if n <= 0:
        return 0.0, 1.0
    if not 0 <= successes <= n:
        raise ValueError(f"successes={successes} outside 0..{n}")
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def gate(passes: int, fails: int, gate_cfg, z: float = WILSON_Z) -> Dict[str, Any]:
    """The statistical verdict of one dimension: pass | fail | insufficient_samples | no_decided_runs."""
    n = passes + fails
    out: Dict[str, Any] = {"n": n, "passes": passes, "fails": fails, "pass_rate": None, "ci_low": None,
                           "ci_high": None, "min_lower_bound": gate_cfg.min_lower_bound,
                           "max_failures": gate_cfg.max_failures}
    if n == 0:
        return {**out, "verdict": "no_decided_runs", "reason": "no run was decided (all undecided or not run)"}
    low, high = wilson(passes, n, z)
    out.update(pass_rate=round(passes / n, 4), ci_low=round(low, 4), ci_high=round(high, 4))
    if gate_cfg.max_failures is not None and fails > gate_cfg.max_failures:
        return {**out, "verdict": "fail",
                "reason": f"{fails} failed run(s) > {gate_cfg.max_failures} allowed (zero-tolerance dimension)"}
    if low >= gate_cfg.min_lower_bound:
        return {**out, "verdict": "pass", "reason": f"lower bound {low:.3f} ≥ {gate_cfg.min_lower_bound}"}
    best = wilson(n, n, z)[0]
    if fails == 0 and best < gate_cfg.min_lower_bound:
        return {**out, "verdict": "insufficient_samples",
                "reason": f"{n} run(s) cannot reach a lower bound of {gate_cfg.min_lower_bound} even with no failure "
                          f"(best {best:.3f}); raise k or add cases"}
    return {**out, "verdict": "fail", "reason": f"lower bound {low:.3f} < {gate_cfg.min_lower_bound}"}


def case_summary(outcomes: Sequence[str]) -> Dict[str, Any]:
    """k outcomes of one case → counts, pass rate and the non-deterministic flag (both pass and fail seen)."""
    passes = sum(1 for o in outcomes if o == "pass")
    fails = sum(1 for o in outcomes if o == "fail")
    n = passes + fails
    low, high = wilson(passes, n) if n else (None, None)
    return {"k": len(outcomes), "passes": passes, "fails": fails,
            "undecided": len(outcomes) - n, "pass_rate": round(passes / n, 4) if n else None,
            "ci_low": None if low is None else round(low, 4), "ci_high": None if high is None else round(high, 4),
            "non_deterministic": passes > 0 and fails > 0}


def stability(rates_by_dimension: Dict[str, List[Optional[float]]], max_variance: float) -> Dict[str, Any]:
    """Pass-rate variance per dimension across repeated runs of the whole suite (AC 3)."""
    dims: Dict[str, Any] = {}
    for dim, rates in rates_by_dimension.items():
        vals = [r for r in rates if r is not None]
        if len(vals) < 2:
            dims[dim] = {"rates": rates, "variance": None, "ok": None}
            continue
        var = pvariance(vals)
        dims[dim] = {"rates": rates, "variance": round(var, 5), "ok": var <= max_variance}
    judged = [d for d in dims.values() if d["ok"] is not None]
    return {"max_variance": max_variance, "dimensions": dims,
            "ok": all(d["ok"] for d in judged) if judged else None,
            "worst": max((d["variance"] for d in judged), default=None)}
