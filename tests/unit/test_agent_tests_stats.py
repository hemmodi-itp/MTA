"""Statistical verdicts (tools/agent_tests/stats.py, Phase 9.4): Wilson interval, gates, case summary, stability."""

import math

import pytest

from tools.agent_tests.spec import GateCfg
from tools.agent_tests.stats import case_summary, gate, stability, wilson

pytestmark = pytest.mark.mta


@pytest.mark.parametrize("k,n,low,high", [
    (8, 10, 0.4902, 0.9433),    # textbook value (p = 0.8, n = 10)
    (10, 10, 0.7225, 1.0),
    (0, 10, 0.0, 0.2775),
    (28, 30, 0.7868, 0.9815),
    (50, 100, 0.4038, 0.5962),
])
def test_wilson_reference_values(k, n, low, high):
    lo, hi = wilson(k, n)
    assert math.isclose(lo, low, abs_tol=5e-4) and math.isclose(hi, high, abs_tol=5e-4)


def test_wilson_edges():
    assert wilson(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        wilson(11, 10)
    lo1, _ = wilson(15, 15)
    lo2, _ = wilson(30, 30)
    assert lo2 > lo1  # more evidence → tighter interval


def test_gate_pass_fail_insufficient_and_zero_tolerance():
    g = GateCfg(min_lower_bound=0.75)
    assert gate(36, 0, g)["verdict"] == "pass"
    assert gate(20, 16, g)["verdict"] == "fail"
    small = gate(3, 0, g)  # 3/3 → best lower bound 0.44: cannot reach 0.75 whatever happens
    assert small["verdict"] == "insufficient_samples" and "raise k" in small["reason"]
    assert gate(2, 1, g)["verdict"] == "fail"  # failures observed and the bound is missed: a fail, not "insufficient"
    safety = GateCfg(min_lower_bound=0.75, max_failures=0)
    assert gate(39, 1, safety)["verdict"] == "fail" and "zero-tolerance" in gate(39, 1, safety)["reason"]
    assert gate(40, 0, safety)["verdict"] == "pass"
    assert gate(0, 0, g)["verdict"] == "no_decided_runs"
    r = gate(28, 2, g)
    assert r["pass_rate"] == pytest.approx(0.9333, abs=1e-4) and r["ci_low"] < r["pass_rate"] < r["ci_high"]


def test_case_summary_flags_non_determinism():
    s = case_summary(["pass", "fail", "pass", "needs_judge"])
    assert s["non_deterministic"] and s["passes"] == 2 and s["fails"] == 1 and s["undecided"] == 1
    assert s["pass_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert not case_summary(["pass"] * 3)["non_deterministic"]
    assert case_summary(["needs_judge"])["pass_rate"] is None


def test_stability_variance():
    r = stability({"a": [0.9, 0.9, 0.9], "b": [0.5, 0.9, 0.7], "c": [None, 0.8], "d": [None, None]}, 0.01)
    assert r["dimensions"]["a"]["variance"] == 0 and r["dimensions"]["a"]["ok"]
    assert r["dimensions"]["b"]["variance"] == pytest.approx(0.02667, abs=1e-4) and not r["dimensions"]["b"]["ok"]
    assert r["dimensions"]["c"]["ok"] is None and r["dimensions"]["d"]["variance"] is None
    assert r["ok"] is False and r["worst"] == pytest.approx(0.02667, abs=1e-4)
    assert stability({"a": [0.8, 0.85]}, 0.01)["ok"] is True
