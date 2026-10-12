"""
consistency.py — are N replies to the same input semantically equivalent? (design D8)

    score(["Open 9am-6pm.", "We open at 9am and close 6pm."], threshold=0.8)

Two signals, both deterministic:
  * key facts — numbers, times, money, weekdays, yes/no — must not conflict. Two replies conflict when neither's fact
    set contains the other's ("9am-6pm" vs "10am-8pm"): that is a FAIL, the inconsistency that matters to a customer.
    When one reply only omits facts the other states ("free over $50" vs "free over $50, 3-5 days"), nothing is
    contradicted: UNSURE, and the judge decides whether the omission matters (found on the real-LLM benchmark).
  * pairwise lexical similarity (Dice over content-word sets) must reach the threshold. If only this fails, the
    replies may be paraphrases of each other, so the result is UNSURE (an LLM judge decides in Phase 9.3).
"""

import itertools
import re
from dataclasses import dataclass
from typing import FrozenSet, List, Tuple

_NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_DAYS = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b", re.I)
_YESNO = re.compile(r"^\W*(yes|no)\b", re.I)
_WORD = re.compile(r"[a-z0-9']+")
_STOP = set("a an the and or of to in on at for with is are was were be it this that we you your our i my me "
            "can will do does from by as".split())


def key_facts(text: str) -> FrozenSet[str]:
    t = text or ""
    facts = set()
    for h, m, ap in _TIME.findall(t):
        facts.add(f"time:{int(h)}:{m or '00'}{ap.lower()}")
    t_wo_times = _TIME.sub(" ", t)
    for n in _NUM.findall(t_wo_times):
        facts.add("num:" + n.replace(",", ""))
    for d in _DAYS.findall(t):
        facts.add("day:" + d.lower())
    m = _YESNO.search(t)
    if m:
        facts.add("yn:" + m.group(1).lower())
    return frozenset(facts)


def similarity(a: str, b: str) -> float:
    wa = {w for w in _WORD.findall((a or "").lower()) if w not in _STOP}
    wb = {w for w in _WORD.findall((b or "").lower()) if w not in _STOP}
    if not wa and not wb:
        return 1.0
    return 2 * len(wa & wb) / (len(wa) + len(wb))


@dataclass(frozen=True)
class ConsistencyResult:
    result: str            # pass | fail | unsure
    min_similarity: float
    detail: str
    fact_sets: Tuple[Tuple[str, ...], ...]


def score(replies: List[str], threshold: float = 0.8) -> ConsistencyResult:
    if len(replies) < 2:
        return ConsistencyResult("unsure", 1.0, "fewer than two replies to compare", ())
    facts = [key_facts(r) for r in replies]
    sims = [similarity(a, b) for a, b in itertools.combinations(replies, 2)]
    lo = round(min(sims), 3)
    fact_sets = tuple(tuple(sorted(f)) for f in facts)
    pairs = list(itertools.combinations(range(len(facts)), 2))
    conflict = next(((i, j) for i, j in pairs if not (facts[i] <= facts[j] or facts[j] <= facts[i])), None)
    if conflict:
        i, j = conflict
        diff = sorted(facts[i] ^ facts[j])
        return ConsistencyResult("fail", lo, f"replies {i + 1} and {j + 1} disagree on key facts: {', '.join(diff)}",
                                 fact_sets)
    partial = next(((i, j) for i, j in pairs if facts[i] != facts[j]), None)
    if partial:  # one reply states fewer facts but contradicts none: incomplete, not inconsistent — judge decides
        i, j = partial
        return ConsistencyResult("unsure", lo, f"reply {i + 1 if len(facts[i]) < len(facts[j]) else j + 1} omits "
                                 f"facts the other states ({', '.join(sorted(facts[i] ^ facts[j]))}) but none conflict",
                                 fact_sets)
    if lo < threshold:
        return ConsistencyResult("unsure", lo, f"same key facts, but wording similarity {lo:.2f} < {threshold:.2f}",
                                 fact_sets)
    return ConsistencyResult("pass", lo, f"{len(replies)} replies agree (min similarity {lo:.2f})", fact_sets)
