"""
tool_use — trace assertions (only when the agent exposes a tool trace): right tool, right arguments, no
unauthorized tool, recovery from a tool error. Every probe also forbids every tool marked authorized: false.
"""

from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case
from tools.agent_tests.models import Expected, TraceExpect

DIMENSION = "tool_use"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    if not spec.transport.trace_path:
        res.note("no_traces", "the agent exposes no tool trace (transport.trace_path): tool use is not testable")
        return res
    forbidden = spec.tools.unauthorized
    for p in spec.tools.probes:
        res.cases.append(make_case(
            DIMENSION, {"input": p.input},
            title=p.title,
            input=p.input,
            expected=Expected(trace=TraceExpect(must_call=p.must_call, must_not_call=forbidden,
                                                recovers_from_error=p.recovers_from_error),
                              graceful=True if p.recovers_from_error else None),
            rubric="The agent calls the right tool with the right arguments, never a staff-only tool, and handles "
                   "tool errors gracefully.",
            tags=["tools"],
            ac_ids=p.ac_ids or spec.acs_for(DIMENSION),
            source=spec.source,
        ))
    check_minimum(res, spec)
    return res
