"""
multi_turn — context across turns: a turn-1 fact recalled at turn N, a user correction, a topic switch.

Needs session support (transport.history server or client); otherwise every case is cut with no_session_support.
Filler turns are the spec's own task examples, so the conversation stays in-domain.
"""

from tools.agent_tests.generators.base import GeneratorResult, check_minimum, make_case
from tools.agent_tests.generators.task_success import base_examples
from tools.agent_tests.models import Expected, Turn

DIMENSION = "multi_turn"


def generate(spec, catalogs, seed: int) -> GeneratorResult:
    res = GeneratorResult(DIMENSION)
    if not spec.transport.sessions:
        res.note("no_session_support", "transport.history is 'none': conversations cannot span turns")
        return res
    fillers = [ex.input for _, ex in base_examples(spec)]
    acs = spec.acs_for(DIMENSION)
    n_turns = max(3, spec.thresholds.multi_turn_turns)

    def fill(k: int, offset: int = 0):
        return [Turn(user=fillers[(offset + i) % len(fillers)]) for i in range(k)] if fillers else []

    for fact in spec.memory.facts:
        v0, v1 = fact.values[0], fact.values[1]
        turns = [Turn(user=fact.set.format(value=v0))] + fill(n_turns - 2) + [Turn(user=fact.ask)]
        res.cases.append(make_case(
            DIMENSION, {"kind": "recall", "fact": fact.kind, "turns": n_turns},
            title=f"turn-1 {fact.kind} recalled at turn {len(turns)}",
            turns=turns,
            expected=Expected(contains_all=[v0]),
            rubric=f"At the last turn the agent still knows the {fact.kind} given in turn 1 ({v0}).",
            tags=["memory", "recall"], ac_ids=acs, source=spec.source,
        ))
        if fact.correction:
            turns = [Turn(user=fact.set.format(value=v0))] + fill(1, 1) + \
                    [Turn(user=fact.correction.format(value=v1)), Turn(user=fact.ask)]
            res.cases.append(make_case(
                DIMENSION, {"kind": "correction", "fact": fact.kind},
                title=f"user corrects their {fact.kind}",
                turns=turns,
                expected=Expected(contains_all=[v1], not_contains=[v0]),
                rubric=f"The agent uses the corrected {fact.kind} ({v1}), not the first one ({v0}).",
                tags=["memory", "correction"], ac_ids=acs, source=spec.source,
            ))
    pairs = base_examples(spec)
    switch = next(((a, b) for a in pairs for b in pairs if a[0].id != b[0].id), None)
    if switch:
        (ac_a, ex_a), (ac_b, ex_b) = switch
        res.cases.append(make_case(
            DIMENSION, {"kind": "topic_switch", "a": ex_a.input, "b": ex_b.input},
            title=f"topic switch {ac_a.id} → {ac_b.id}",
            turns=[Turn(user=ex_a.input), Turn(user=ex_b.input)],
            expected=ex_b.expect,
            rubric="After the topic changes, the agent answers the new question, not the previous one.",
            tags=["topic_switch"], ac_ids=acs or [ac_b.id], source=spec.source,
        ))
    if not spec.memory.facts:
        res.note("spec_lacks_material", "agent.yaml lists no memory facts (memory.facts)")
    check_minimum(res, spec)
    return res
