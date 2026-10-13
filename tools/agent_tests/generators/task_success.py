"""task_success — one case per acceptance-criterion example in the spec: the user goal is achieved."""

from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case

DIMENSION = "task_success"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    for ac in spec.acs:
        for i, ex in enumerate(ac.examples):
            res.cases.append(make_case(
                DIMENSION, {"ac": ac.id, "input": ex.input},
                title=ex.title or f"{ac.id} example {i + 1}",
                input=ex.input,
                expected=ex.expect,
                rubric=f"The reply achieves the user's goal and satisfies: {ac.statement}",
                tags=["task"],
                ac_ids=[ac.id],
                source=spec.source,
            ))
    if not any(ac.examples for ac in spec.acs):
        res.note("spec_lacks_material", "no acceptance criterion in agent.yaml has examples")
    check_minimum(res, spec)
    return res


def base_examples(spec):
    """(ac, example) pairs in spec order — the material robustness, consistency and latency reuse."""
    return [(ac, ex) for ac in spec.acs for ex in ac.examples]
