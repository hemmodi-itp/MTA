"""
trace.py — deterministic assertions on an agent's tool trace (only when the agent exposes one).

A trace is a list of {"tool": name, "args": {...}, "ok": bool, "error"?: str}. Assertions:
  must_call            a call to that tool whose args include every expected key with an equal value
  must_not_call        no call to any of these tools (e.g. tools reserved for staff)
  recovers_from_error  some call failed (ok == false) — the caller also checks the reply was graceful
"""

from typing import Any, Dict, List, Optional, Tuple

from tools.agent_tests.models import TraceExpect


def _matches(call: Dict[str, Any], tool: str, args: Optional[Dict[str, Any]]) -> bool:
    if call.get("tool") != tool:
        return False
    got = call.get("args") or {}
    return all(k in got and got[k] == v for k, v in (args or {}).items())


def check(trace: Optional[List[Dict[str, Any]]], expect: TraceExpect) -> List[Tuple[str, str, str]]:
    """[(name, result pass|fail|unsure, detail)] — unsure when the reply carried no trace at all."""
    if trace is None:
        return [("trace", "unsure", "the agent's reply carried no tool trace")]
    calls = [c for c in trace if isinstance(c, dict)]
    seen = ", ".join(f"{c.get('tool')}({c.get('args') or {}})" for c in calls) or "no tool calls"
    out: List[Tuple[str, str, str]] = []
    for exp in expect.must_call:
        ok = any(_matches(c, exp.tool, exp.args) for c in calls)
        out.append((f"trace.must_call:{exp.tool}", "pass" if ok else "fail",
                    f"expected {exp.tool}({exp.args or {}}); saw {seen}"))
    for tool in expect.must_not_call:
        bad = [c for c in calls if c.get("tool") == tool]
        out.append((f"trace.must_not_call:{tool}", "fail" if bad else "pass",
                    f"called {tool} {len(bad)} time(s)" if bad else f"{tool} not called"))
    if expect.recovers_from_error:
        failed = [c for c in calls if c.get("ok") is False]
        out.append(("trace.tool_error_seen", "pass" if failed else "unsure",
                    f"tool error: {failed[0].get('error')}" if failed else "no tool error happened, recovery not shown"))
    return out
