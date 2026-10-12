"""
latency.py — latency / token percentiles against the agent's budgets (nearest-rank percentiles).

Time-to-first-token equals total time for non-streaming transports (HTTP JSON); the report says so.
"""

import math
from typing import Dict, List, Optional, Sequence


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(s)))
    return float(s[rank - 1])


def budget_checks(latencies_ms: List[float], tokens_per_turn: List[float], budgets) -> List[Dict]:
    """[{name, result, detail, value, budget}] for p50 / p95 latency and p95 tokens per turn."""
    out: List[Dict] = []
    for name, p, limit in (("latency.p50_ms", 50, budgets.p50_ms), ("latency.p95_ms", 95, budgets.p95_ms)):
        value = percentile(latencies_ms, p)
        if limit is None or value is None:
            out.append({"name": name, "result": "not_applicable", "value": value, "budget": limit,
                        "detail": "no budget" if limit is None else "no successful requests"})
            continue
        ok = value <= limit
        out.append({"name": name, "result": "pass" if ok else "fail", "value": round(value, 1), "budget": limit,
                    "detail": f"{value:.0f} ms {'≤' if ok else '>'} {limit:.0f} ms over {len(latencies_ms)} requests"})
    limit = budgets.max_tokens_per_turn_p95
    value = percentile(tokens_per_turn, 95)
    if limit is None or value is None:
        out.append({"name": "tokens.p95_per_turn", "result": "not_applicable", "value": value, "budget": limit,
                    "detail": "the agent reports no token usage" if value is None else "no budget"})
    else:
        ok = value <= limit
        out.append({"name": "tokens.p95_per_turn", "result": "pass" if ok else "fail", "value": value, "budget": limit,
                    "detail": f"{value:.0f} tokens {'≤' if ok else '>'} {limit:.0f} per turn"})
    return out
