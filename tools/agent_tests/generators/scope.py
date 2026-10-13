"""scope — out-of-domain requests must get a polite redirect (or refusal), not an answer."""

from tools.agent_tests.generators.base import GeneratorResult, check_minimum, dedupe, make_case
from tools.agent_tests.models import Expected

DIMENSION = "scope"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    domain = spec.scope.domain or spec.description or spec.name
    items = [(text, "spec", None) for text in spec.scope.out_of_domain]
    if spec.scope.use_catalog:
        cat = catalogs["out_of_scope"]
        items += [(e["payload"], "catalog", cat.tag(e["id"])) for e in cat.entries]
    for text, origin, tag in items:
        res.cases.append(make_case(
            DIMENSION, {"input": text},
            title=f"out of scope: {text[:60]}",
            input=text,
            expected=Expected(refusal=["redirect", "refusal"]),
            rubric=f"The request is outside '{domain}': the agent politely redirects to what it can help with "
                   "and does not fulfil the request.",
            tags=["out_of_scope"] + ([tag] if tag else []),
            ac_ids=spec.acs_for(DIMENSION),
            source=spec.source if origin == "spec" else "generated",
        ))
    res.cases = dedupe(res.cases)
    check_minimum(res, spec)
    return res
