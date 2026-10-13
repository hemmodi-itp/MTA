"""groundedness — knowledge-base questions: the reply states the document's facts and cites that document."""

from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case
from tools.agent_tests.models import Expected

DIMENSION = "groundedness"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    fmt = spec.kb.citation_format
    for doc in spec.kb.docs:
        res.cases.append(make_case(
            DIMENSION, {"doc": doc.id, "question": doc.question},
            title=f"grounded in '{doc.title}'",
            input=doc.question,
            context={"kb_doc": doc.id, "facts": doc.facts},
            expected=Expected(contains_all=doc.facts, cites=fmt.format(title=doc.title) if fmt else None),
            rubric=(f"Every claim in the reply is supported by the knowledge-base document '{doc.title}' "
                    f"(facts: {'; '.join(doc.facts)}); nothing is added that the document does not say"
                    + ("; the reply cites that document." if fmt else ".")),
            tags=["kb"],
            ac_ids=doc.ac_ids or spec.acs_for(DIMENSION),
            source=spec.source,
        ))
    if not spec.kb.docs:
        res.note("spec_lacks_material", "agent.yaml lists no knowledge-base documents (kb.docs)")
    check_minimum(res, spec)
    return res
