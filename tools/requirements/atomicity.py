"""
atomicity.py — deterministic check that an acceptance criterion states ONE checkable behaviour (Phase 1.1).

Agent-Eval only asks the LLM for atomic criteria (audit A11); nothing verified it. This flags criteria that
clearly bundle several behaviours, so the extraction LLM's split can be required and validated, and an unsplit
compound criterion is reported instead of silently counted as one behaviour. The rules favour precision:
restating one behaviour twice ("Name is required; an empty name is rejected") is not flagged. The LLM may still
split any criterion; this check only decides which ones must not stay whole without a warning.

Signals (any one → not atomic):
  multiple_messages            different expected messages stated in different clauses
  positive_and_negative        an accept/allow outcome and a reject/deny outcome in the same criterion
  multiple_conditions          ≥ 2 clauses, each with its own condition ("when …", "anything else …") and outcome
"""

import re
from typing import List, Tuple

_QUOTED_RE = re.compile(r"\"([^\"]{3,})\"|“([^”]{3,})”")
# A sentence break: ". " followed by an upper-case letter (not "e.g. x", not "1.005").
_SENTENCE_RE = re.compile(r"(?<=[a-z0-9\)\"”`])[.!?]\s+(?=[A-Z])")
_POSITIVE = re.compile(
    r"\b(?:is|are|be)\s+accepted\b|\baccepts?\b|\bsucceeds?\b|\bcan\s+(?:see|access|open|view|use)\b"
    r"|\bis\s+available\b|\bis\s+allowed\b|\bare\s+allowed\b", re.IGNORECASE)
_NEGATIVE = re.compile(
    r"\b(?:is|are|be)\s+rejected\b|\brejects?\b|\bdenied\b|\bforbidden\b|\bHTTP\s*40[13]\b|\bis\s+blocked\b",
    re.IGNORECASE)
_CONDITION = re.compile(
    r"\b(?:when|whenever|if|unless|given|for)\b|\banything else\b|\bany other\b|\bunknown\b|\bover\s+\d",
    re.IGNORECASE)
_OUTCOME = re.compile(
    r"\b(?:must|shall|is|are|shows?|returns?|gets?|rejected|accepted|displays?|creates?|redirects?|opens?)\b",
    re.IGNORECASE)


def _clauses(statement: str) -> List[str]:
    parts: List[str] = []
    for chunk in statement.split(";"):
        parts.extend(p for p in _SENTENCE_RE.split(chunk) if p.strip())
    return [p.strip() for p in parts if p.strip()]


def _messages(clause: str) -> set:
    return {(a or b).strip().lower() for a, b in _QUOTED_RE.findall(clause)}


def check(statement: str) -> Tuple[bool, List[str]]:
    """(atomic, issues). Deterministic; never raises."""
    text = re.sub(r"\s+", " ", statement or "").strip()
    if not text:
        return True, []
    issues: List[str] = []
    clauses = _clauses(text)

    with_messages = [m for m in (_messages(c) for c in clauses) if m]
    if len(with_messages) >= 2 and len(set().union(*with_messages)) >= 2:
        issues.append("multiple_messages")

    bare = _QUOTED_RE.sub('"Q"', text)   # quoted UI text must not count as the criterion's own outcome words
    if _POSITIVE.search(bare) and _NEGATIVE.search(bare):
        issues.append("positive_and_negative")

    conditioned = [c for c in _clauses(bare) if _CONDITION.search(c) and _OUTCOME.search(c)]
    if len(conditioned) >= 2:
        issues.append("multiple_conditions")

    return (not issues), issues
