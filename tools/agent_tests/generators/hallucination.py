"""hallucination — in-domain questions the knowledge base does NOT answer: the agent must say it does not know."""

from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case
from tools.agent_tests.models import Expected

DIMENSION = "hallucination"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    for q in spec.kb.unanswerable:
        res.cases.append(make_case(
            DIMENSION, {"question": q.question},
            title=f"no answer in the KB: {q.question[:60]}",
            input=q.question,
            expected=Expected(refusal=["dont_know"]),
            rubric="The knowledge base has no answer: the reply says it does not know and invents no details.",
            tags=["no_answer"],
            ac_ids=q.ac_ids or spec.acs_for(DIMENSION),
            source=spec.source,
        ))
    if not spec.kb.unanswerable:
        res.note("spec_lacks_material", "agent.yaml lists no unanswerable questions (kb.unanswerable)")
    check_minimum(res, spec)
    return res
