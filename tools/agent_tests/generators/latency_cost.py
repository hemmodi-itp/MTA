"""
latency_cost — probe cases that guarantee enough timing samples. The verdict is computed over EVERY request of the
run (p50 / p95 time, p95 tokens per turn) against agent.yaml `budgets`, not per probe.
"""

from tools.agent_tests.config import MIN_CASES
from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case
from tools.agent_tests.generators.task_success import base_examples

DIMENSION = "latency_cost"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    b = spec.budgets
    for i, (ac, ex) in enumerate(base_examples(spec)[:MIN_CASES[DIMENSION]]):
        res.cases.append(make_case(
            DIMENSION, {"probe": i, "input": ex.input},
            title=f"latency probe {i + 1}",
            input=ex.input,
            rubric=f"Budgets: p50 ≤ {b.p50_ms} ms, p95 ≤ {b.p95_ms} ms, p95 tokens/turn ≤ {b.max_tokens_per_turn_p95}.",
            tags=["latency"],
            ac_ids=b.ac_ids or spec.acs_for(DIMENSION),
            source=spec.source,
        ))
    check_minimum(res, spec)
    return res
