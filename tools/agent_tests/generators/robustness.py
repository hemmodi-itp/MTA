"""
robustness — perturbed versions of task-success cases must get the same verdict as the original.

Per base case (the first `thresholds.robustness_bases`, preferring examples that carry paraphrases/translations):
typo (seeded adjacent-letter swap), UPPER CASE, chat slang, the spec's first paraphrase and translation; the first
base also gets a very long input. Plus empty and emoji-only messages, which must get a graceful reply.
"""

import re

from tools.agent_tests.generators import task_success
from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case, rng
from tools.agent_tests.models import Expected

DIMENSION = "robustness"
_WORD = re.compile(r"[A-Za-z]+")


def typo(text: str, seed: int, key: str) -> str:
    """Swap two adjacent interior letters of one word of 5+ letters (seeded); unchanged if there is no such word."""
    r = rng(seed, f"typo:{key}")
    words = [m for m in _WORD.finditer(text) if len(m.group(0)) >= 5]
    if not words:
        return text
    m = r.choice(words)
    w = m.group(0)
    positions = [i for i in range(1, len(w) - 2) if w[i] != w[i + 1]] or [1]
    i = r.choice(positions)
    swapped = w[:i] + w[i + 1] + w[i] + w[i + 2:]
    return text[:m.start()] + swapped + text[m.end():]


def slang(text: str, table: dict) -> str:
    out = text
    for word, short in table.items():
        out = re.sub(rf"\b{re.escape(word)}\b", short, out, flags=re.I)
    return out.lower()


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    cat = catalogs["robustness"]
    data, tag = cat.data, f"catalog:robustness@{cat.version}"
    bases = task_success.generate(spec, catalogs, seed).cases
    examples = {(ac.id, ex.input): ex for ac, ex in task_success.base_examples(spec)}
    by_case = [(c, examples[(c.ac_ids[0], c.input)]) for c in bases if (c.ac_ids[0], c.input) in examples]
    by_case.sort(key=lambda ce: 0 if (ce[1].paraphrases or ce[1].translations) else 1)  # stable: spec order kept
    chosen = by_case[:spec.thresholds.robustness_bases]

    def variant(base, kind: str, text: str) -> None:
        if text == base.input:
            return
        res.cases.append(make_case(
            DIMENSION, {"base": base.id, "kind": kind, "input": text},
            title=f"{kind} of {base.id}",
            input=text,
            expected=base.expected.model_copy(update={"same_as": base.id}),
            rubric=f"Same outcome as {base.id} despite the {kind}.",
            tags=[f"perturbation:{kind}", tag],
            ac_ids=base.ac_ids + [a for a in spec.acs_for(DIMENSION) if a not in base.ac_ids],
            source="generated",
        ))

    for n, (base, ex) in enumerate(chosen):
        variant(base, "typo", typo(base.input, seed, base.id))
        variant(base, "upper_case", base.input.upper())
        variant(base, "slang", slang(base.input, data.get("slang") or {}))
        if ex.paraphrases:
            variant(base, "paraphrase", ex.paraphrases[0])
        if ex.translations:
            variant(base, "other_language", ex.translations[0])
        if n == 0:
            filler = data.get("filler_sentence") or "Some unrelated background text. "
            reps = max(1, spec.thresholds.long_input_chars // len(filler))
            variant(base, "very_long", filler * reps + base.input)
    if chosen and not any(ex.paraphrases for _, ex in chosen):
        res.note("spec_lacks_material", "no paraphrases in agent.yaml: paraphrase variants not generated")
    if chosen and not any(ex.translations for _, ex in chosen):
        res.note("spec_lacks_material", "no translations in agent.yaml: other-language variants not generated")

    graceful = Expected(graceful=True, canary_absent=["CANARY_SYS"])
    for kind, text in (("empty", (data.get("empty_inputs") or [""])[0]), ("emoji_only", data.get("emoji_only") or "🤔")):
        res.cases.append(make_case(
            DIMENSION, {"kind": kind, "input": text},
            title=f"{kind.replace('_', ' ')} message",
            input=text,
            expected=graceful,
            rubric="A friendly reply (e.g. asking what the user needs), never an error.",
            tags=[f"perturbation:{kind}", tag],
            ac_ids=spec.acs_for(DIMENSION),
            source="generated",
        ))
    check_minimum(res, spec)
    return res
