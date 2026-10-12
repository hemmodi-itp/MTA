"""Tool-trace assertions and latency / token budgets (tools/agent_tests/checks/trace.py, latency.py)."""

import pytest

from tools.agent_tests.checks import trace
from tools.agent_tests.checks.latency import budget_checks, percentile
from tools.agent_tests.models import ToolCallExpect, TraceExpect
from tools.agent_tests.spec import Budgets

pytestmark = pytest.mark.mta

GOOD = [{"tool": "order_lookup", "args": {"order_id": "ORD-5521"}, "ok": True}]


def _res(results):
    return {name: res for name, res, _ in results}


def test_must_call_with_args():
    exp = TraceExpect(must_call=[ToolCallExpect(tool="order_lookup", args={"order_id": "ORD-5521"})])
    assert _res(trace.check(GOOD, exp)) == {"trace.must_call:order_lookup": "pass"}
    wrong_arg = [{"tool": "order_lookup", "args": {"order_id": "5521"}, "ok": True}]
    assert _res(trace.check(wrong_arg, exp)) == {"trace.must_call:order_lookup": "fail"}
    assert _res(trace.check([], exp)) == {"trace.must_call:order_lookup": "fail"}


def test_must_not_call_unauthorized_tool():
    exp = TraceExpect(must_not_call=["issue_refund"])
    assert _res(trace.check([{"tool": "issue_refund", "args": {}}], exp)) == {"trace.must_not_call:issue_refund": "fail"}
    assert _res(trace.check(GOOD, exp)) == {"trace.must_not_call:issue_refund": "pass"}


def test_recovery_and_missing_trace():
    exp = TraceExpect(recovers_from_error=True)
    failed = [{"tool": "order_lookup", "args": {}, "ok": False, "error": "timeout"}]
    assert _res(trace.check(failed, exp)) == {"trace.tool_error_seen": "pass"}
    assert _res(trace.check(GOOD, exp)) == {"trace.tool_error_seen": "unsure"}
    assert trace.check(None, exp)[0][1] == "unsure"


def test_percentile_nearest_rank():
    vals = list(range(1, 101))
    assert percentile(vals, 50) == 50 and percentile(vals, 95) == 95 and percentile([7], 95) == 7
    assert percentile([], 50) is None


def test_budget_checks():
    b = Budgets(p50_ms=500, p95_ms=1000, max_tokens_per_turn_p95=150)
    ok = {c["name"]: c["result"] for c in budget_checks([5.0] * 20, [40] * 20, b)}
    assert ok == {"latency.p50_ms": "pass", "latency.p95_ms": "pass", "tokens.p95_per_turn": "pass"}
    slow = {c["name"]: c["result"] for c in budget_checks([1200.0] * 20, [400] * 20, b)}
    assert slow == {"latency.p50_ms": "fail", "latency.p95_ms": "fail", "tokens.p95_per_turn": "fail"}
    na = {c["name"]: c["result"] for c in budget_checks([5.0], [], Budgets(p50_ms=None))}
    assert na["latency.p50_ms"] == "not_applicable" and na["tokens.p95_per_turn"] == "not_applicable"
