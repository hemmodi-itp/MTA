"""
generators — one deterministic generator per Phase 9.1 dimension.

    results = generate_all(spec, catalogs, seed=7)   # {dimension: GeneratorResult(cases, cut)}

Disabled dimensions and red-team dimensions without authorization (design D10) produce no cases; the reason is
recorded in `cut` so the report can say what was not tested and why.
"""

from typing import Dict

from tools.agent_tests.generators import (consistency, data_leakage, groundedness, hallucination, harmful_refusal,
                                          instruction_format, latency_cost, multi_turn, prompt_injection_direct,
                                          prompt_injection_indirect, robustness, scope, session_isolation,
                                          task_success, tool_use)
from tools.agent_tests.generators.base import GeneratorResult
from tools.agent_tests.models import DIMENSIONS, RED_TEAM

GENERATORS = {
    "task_success": task_success.generate,
    "groundedness": groundedness.generate,
    "hallucination": hallucination.generate,
    "consistency": consistency.generate,
    "robustness": robustness.generate,
    "multi_turn": multi_turn.generate,
    "instruction_format": instruction_format.generate,
    "scope": scope.generate,
    "prompt_injection_direct": prompt_injection_direct.generate,
    "prompt_injection_indirect": prompt_injection_indirect.generate,
    "data_leakage": data_leakage.generate,
    "harmful_refusal": harmful_refusal.generate,
    "tool_use": tool_use.generate,
    "session_isolation": session_isolation.generate,
    "latency_cost": latency_cost.generate,
}
assert tuple(GENERATORS) == DIMENSIONS


def generate_all(spec, catalogs, seed: int = 0) -> Dict[str, GeneratorResult]:
    out: Dict[str, GeneratorResult] = {}
    for dim in DIMENSIONS:
        res = GeneratorResult(dim)
        if not spec.dimension_enabled(dim):
            res.note("disabled", f"{dim} is disabled in agent.yaml"
                     + (" (auto: the agent exposes no tool trace)" if dim == "tool_use" else ""))
        elif dim in RED_TEAM and not spec.authorization.owned_or_authorized:
            res.note("not_authorized", "red-team tests run only against agents the owner has authorised "
                                       "(agent.yaml authorization.owned_or_authorized)")
        else:
            res = GENERATORS[dim](spec, catalogs, seed)
        out[dim] = res
    return out
