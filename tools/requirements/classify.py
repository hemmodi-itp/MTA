"""
classify.py — deterministic classification of acceptance criteria (Phase 1.1).

  risk_tags_for()        keyword catalog (risk_rules.yaml) ∪ the LLM's tags filtered to the closed enum
  resolve_priority()     BRD-stated P0-P3 > MoSCoW > LLM suggestion > default P2, then the risk floor rule
  heuristic_testability() keyword fallback used when the LLM gave nothing usable
  to_agent_eval_priority() / from_agent_eval_priority()   P0-P3 <-> high / medium / low

The LLM interprets (testability, a priority suggestion); these rules decide whatever is computable.
"""

import os
import re
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

from tools.requirements.models import PRIORITIES, RISK_TAGS, TESTABILITY

_RULES_PATH = os.path.join(os.path.dirname(__file__), "risk_rules.yaml")
DEFAULT_PRIORITY = "P2"
# A risk tag that forces at least this priority (lower number = higher priority).
_RISK_FLOOR = {"auth": "P1", "payment": "P1", "data-loss": "P1"}
_MOSCOW = {"must": "P1", "should": "P2", "could": "P3", "won't": "P3", "wont": "P3", "will not": "P3"}


# ── risk tags ────────────────────────────────────────────────────────────────

def _phrase_regex(phrase: str) -> str:
    phrase = phrase.strip().lower()
    prefix = phrase.endswith("*")
    body = re.escape(phrase.rstrip("*")).replace(r"\ ", r"\s+")
    return rf"(?<![\w-]){body}" + (r"[\w-]*" if prefix else r"(?![\w-])")


@lru_cache(maxsize=4)
def load_risk_rules(path: str = _RULES_PATH) -> Dict[str, "re.Pattern[str]"]:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    rules = {}
    for tag, phrases in raw.items():
        if tag not in RISK_TAGS:
            raise ValueError(f"risk_rules.yaml: unknown risk tag {tag!r} (allowed: {sorted(RISK_TAGS)})")
        rules[tag] = re.compile("|".join(_phrase_regex(str(p)) for p in phrases or []), re.IGNORECASE)
    return rules


def keyword_risk_tags(text: str) -> List[str]:
    return [tag for tag, rx in load_risk_rules().items() if rx.search(text or "")]


def risk_tags_for(text: str, llm_tags: Optional[Iterable[str]] = None) -> List[str]:
    """Keyword-catalog tags plus the LLM's tags that belong to the closed enum, in enum order."""
    tags = set(keyword_risk_tags(text))
    for t in llm_tags or []:
        norm = str(t).strip().lower().replace("_", "-").replace(" ", "-")
        norm = "PII" if norm == "pii" else norm
        if norm in RISK_TAGS:
            tags.add(norm)
    return [t for t in RISK_TAGS if t in tags]


# ── priority ─────────────────────────────────────────────────────────────────

# Only an explicitly marked priority counts ("Priority: P1", "(P0)", "[P2]") — never a bare "P1" in prose.
_STATED_P = re.compile(r"(?:\bpriority\s*[:=]?\s*|[(\[])(P[0-3])\b", re.IGNORECASE)
_STATED_MOSCOW = re.compile(r"\b(?:priority|moscow)\s*[:=]?\s*(must|should|could|won['’]?t|will not)\b", re.IGNORECASE)


def stated_priority(text: str) -> Optional[str]:
    """A priority the document itself states for this item ("Priority: P1", "(P0)", "MoSCoW: Must")."""
    m = _STATED_P.search(text or "")
    if m:
        return m.group(1).upper()
    m = _STATED_MOSCOW.search(text or "")
    if m:
        key = m.group(1).lower().replace("’", "'")
        return _MOSCOW.get(key, _MOSCOW.get(key.replace("'", ""), DEFAULT_PRIORITY))
    return None


def normalise_priority(value: Optional[str]) -> Optional[str]:
    v = str(value or "").strip().upper()
    if v in PRIORITIES:
        return v
    return {"HIGH": "P1", "MEDIUM": "P2", "LOW": "P3", "CRITICAL": "P0"}.get(v)


def resolve_priority(stated: Optional[str], llm_value: Optional[str], risk_tags: Iterable[str]) -> Tuple[str, str]:
    """(priority, priority_source). Precedence: BRD > LLM > default; then the risk floor raises it."""
    if stated:
        priority, source = stated, "brd"
    elif normalise_priority(llm_value):
        priority, source = normalise_priority(llm_value), "llm"
    else:
        priority, source = DEFAULT_PRIORITY, "default"
    for tag in risk_tags:
        floor = _RISK_FLOOR.get(tag)
        if floor and int(floor[1]) < int(priority[1]):
            priority, source = floor, "rule"
    return priority, source


def to_agent_eval_priority(p: str) -> str:
    return {"P0": "high", "P1": "high", "P2": "medium", "P3": "low"}.get(p, "medium")


def from_agent_eval_priority(p: Optional[str]) -> str:
    return {"high": "P1", "medium": "P2", "low": "P3"}.get(str(p or "").lower(), DEFAULT_PRIORITY)


# ── testability ──────────────────────────────────────────────────────────────

_API = re.compile(r"/api/|\bapi\b|\bHTTP\s*[1-5]\d\d\b|\bJSON\b|\bendpoint|\b(GET|POST|PUT|PATCH|DELETE)\s+/", re.IGNORECASE)
_NON_FUNCTIONAL = re.compile(
    r"\bwithin\s+\d+(\.\d+)?\s*(ms|milliseconds?|s|secs?|seconds?|minutes?)\b|\blatency\b|\bload(s|ed)?\s+(with)?in\b"
    r"|\baccessib|\bWCAG\b|\bscreen reader|\bprogrammatically associated\b|\baccessible name\b|\bcontrast\b"
    r"|\bthroughput\b|\bconcurrent users\b|\buptime\b|\bavailability\b",
    re.IGNORECASE,
)
_MANUAL = re.compile(r"\bmanual(ly)?\b|\bvisually inspect|\blegal review\b|\bsign[- ]off\b|\bhuman review\b", re.IGNORECASE)


def heuristic_testability(text: str) -> Tuple[str, str]:
    """(testability, reason) from keywords; used only when the LLM gave nothing usable."""
    if _MANUAL.search(text or ""):
        return "manual_only", "heuristic: the statement describes a manual or human check"
    if _NON_FUNCTIONAL.search(text or ""):
        return "non_functional", "heuristic: the statement is about performance or accessibility"
    if _API.search(text or ""):
        return "api", "heuristic: the statement names an API, HTTP status or JSON payload"
    return "ui", "heuristic: an observable behaviour in the user interface"


def resolve_testability(llm_value: Optional[str], llm_reason: Optional[str], text: str) -> Tuple[str, str, str]:
    """(testability, reason, source). The LLM's value is used when it is in the enum and, for
    manual_only / not_testable, carries a reason; otherwise the keyword heuristic decides."""
    v = str(llm_value or "").strip().lower().replace("-", "_").replace(" ", "_")
    reason = re.sub(r"\s+", " ", str(llm_reason or "")).strip()
    if v in TESTABILITY and (reason or v not in ("manual_only", "not_testable")):
        return v, reason or f"classified as {v}", "llm"
    t, r = heuristic_testability(text)
    return t, r, "heuristic"
