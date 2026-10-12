"""consistency — the same input sent N times (fresh sessions) must get semantically equivalent replies."""

from tools.agent_tests.config import MIN_CASES
from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case
from tools.agent_tests.generators.task_success import base_examples
from tools.agent_tests.models import Expected

DIMENSION = "consistency"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    n = spec.thresholds.consistency_n
    cfg = spec.dimensions.get(DIMENSION)
    count = cfg.min_cases if cfg and cfg.min_cases else MIN_CASES[DIMENSION]
    for ac, ex in base_examples(spec)[:count]:
        res.cases.append(make_case(
            DIMENSION, {"ac": ac.id, "input": ex.input, "n": n},
            title=f"{n}× the same question ({ac.id})",
            input=ex.input,
            expected=Expected(consistent_n=n),
            rubric=f"All {n} replies give the same facts and are semantically equivalent.",
            tags=["repeat"],
            ac_ids=spec.acs_for(DIMENSION) or [ac.id],
            source=spec.source,
        ))
    check_minimum(res, spec)
    return res
