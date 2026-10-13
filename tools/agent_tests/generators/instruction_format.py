"""instruction_format — required output formats: JSON matching a schema, length limits (schema-validated, no LLM)."""

from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case
from tools.agent_tests.models import Expected

DIMENSION = "instruction_format"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    js = spec.format.json_
    if js:
        for q in js.questions:
            text = f"{js.trigger} {q}".strip()
            res.cases.append(make_case(
                DIMENSION, {"kind": "json", "input": text},
                title=f"JSON output: {q[:50]}",
                input=text,
                expected=Expected(json_schema=js.schema_),
                rubric="The reply is only a JSON object that matches the required schema.",
                tags=["format:json"], ac_ids=js.ac_ids or spec.acs_for(DIMENSION), source=spec.source,
            ))
    ln = spec.format.length
    if ln:
        for q in ln.questions:
            res.cases.append(make_case(
                DIMENSION, {"kind": "length", "input": q, "max": ln.max_words},
                title=f"at most {ln.max_words} words: {q[:50]}",
                input=q,
                expected=Expected(max_words=ln.max_words),
                rubric=f"The reply is at most {ln.max_words} words.",
                tags=["format:length"], ac_ids=ln.ac_ids or spec.acs_for(DIMENSION), source=spec.source,
            ))
    if not js and not ln:
        res.note("spec_lacks_material", "agent.yaml states no output format (format.json / format.length)")
    check_minimum(res, spec)
    return res
