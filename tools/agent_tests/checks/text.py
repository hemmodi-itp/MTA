"""
text.py — contains / not-contains / regex / word-count / citation checks on a reply.

Matching is case-insensitive with whitespace collapsed and curly quotes straightened, so "We're" in an expectation
matches "We’re" in a reply. Regexes are used as written (put (?i) in the pattern for case-insensitive matching).
"""

import re
from typing import List, Optional, Tuple

from engines.validation.output import _BROKEN_REPLY  # the evaluation pipeline's "error page / stack trace" signal


def norm(text: str) -> str:
    t = (text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", t).strip().lower()


def contains_all(reply: str, needles: List[str]) -> Tuple[bool, str]:
    r = norm(reply)
    missing = [n for n in needles if norm(n) not in r]
    return (not missing, "all expected text present" if not missing else f"missing: {missing}")


def contains_any(reply: str, needles: List[str]) -> Tuple[bool, str]:
    r = norm(reply)
    hit = next((n for n in needles if norm(n) in r), None)
    return (hit is not None, f"found {hit!r}" if hit else f"none of {needles} present")


def not_contains(reply: str, needles: List[str]) -> Tuple[bool, str]:
    r = norm(reply)
    present = [n for n in needles if norm(n) in r]
    return (not present, "no forbidden text" if not present else f"forbidden text present: {present}")


def regex(reply: str, pattern: str, negate: bool = False) -> Tuple[bool, str]:
    m = re.search(pattern, reply or "")
    if negate:
        return (m is None, "pattern absent" if m is None else f"forbidden pattern matched {m.group(0)!r}")
    return (m is not None, f"matched {m.group(0)!r}" if m else f"pattern {pattern!r} not found")


def word_count(reply: str) -> int:
    return len(re.findall(r"\S+", reply or ""))


def max_words(reply: str, limit: int) -> Tuple[bool, str]:
    n = word_count(reply)
    return (n <= limit, f"{n} words {'≤' if n <= limit else '>'} {limit}")


def graceful(reply: Optional[str]) -> Tuple[bool, str]:
    """A usable reply: not empty and not an error page / stack trace."""
    if not (reply or "").strip():
        return False, "empty reply"
    m = _BROKEN_REPLY.search(reply)
    return (m is None, "friendly reply" if m is None else f"error-like reply ({m.group(0)!r})")
