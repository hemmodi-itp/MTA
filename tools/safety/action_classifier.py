"""
action_classifier.py — deterministic "is this UI action destructive?" check.

No LLM. A step is destructive when it *interacts* with a control whose accessible
name (or locator key / id / test-id words) contains a destructive phrase from
destructive_rules.yaml — delete, remove, pay, purchase, place order, send,
transfer, deactivate, unsubscribe, reset, ... — and no `safe` phrase overrides it,
or when its URL / href matches a destructive URL pattern.

Only interaction actions are classified. verify*/wait*/enterText never are: typing
into a field changes nothing until something is clicked or submitted.
"""

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

import yaml

_RULES_PATH = os.path.join(os.path.dirname(__file__), "destructive_rules.yaml")

# Actions that can trigger a state change on the target element.
INTERACTION_ACTIONS = frozenset({
    "click", "doubleClick", "pressKey", "checkCheckbox", "uncheckCheckbox",
    "selectDropdownByText", "selectDropdownByValue", "dragAndDrop",
})
NAVIGATION_ACTIONS = frozenset({"navigate"})


@dataclass(frozen=True)
class Verdict:
    destructive: bool
    category: Optional[str] = None
    rule: Optional[str] = None
    text: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"destructive": self.destructive, "category": self.category,
                "rule": self.rule, "text": self.text}


@dataclass
class _Rules:
    phrases: List[tuple] = field(default_factory=list)   # (category, phrase, compiled)
    safe: List[re.Pattern] = field(default_factory=list)
    urls: List[re.Pattern] = field(default_factory=list)


def _phrase_regex(phrase: str) -> re.Pattern:
    words = [re.escape(w) for w in phrase.lower().split()]
    return re.compile(r"\b" + r"\s+".join(words) + r"\b")


@lru_cache(maxsize=1)
def _rules() -> _Rules:
    with open(_RULES_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    rules = _Rules()
    for category, phrases in (data.get("destructive") or {}).items():
        for phrase in phrases or []:
            rules.phrases.append((category, phrase, _phrase_regex(phrase)))
    # Longest phrases first, so "cancel subscription" reports before a shorter hit.
    rules.phrases.sort(key=lambda t: -len(t[1]))
    rules.safe = [_phrase_regex(p) for p in data.get("safe") or []]
    rules.urls = [re.compile(p, re.I) for p in data.get("url_patterns") or []]
    return rules


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_WORD = re.compile(r"[^A-Za-z0-9]+")


def words_of(identifier: Optional[str]) -> str:
    """'deleteAccountBtn' / 'delete-account' / '#delete_account' -> 'delete account btn'."""
    if not identifier:
        return ""
    text = _CAMEL.sub(" ", str(identifier))
    return _NON_WORD.sub(" ", text).strip().lower()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def classify_text(text: str) -> Verdict:
    """Classify a control's descriptive text (accessible name + identifier words)."""
    norm = _normalize(text)
    if not norm:
        return Verdict(False, text=norm)
    rules = _rules()
    for safe in rules.safe:
        if safe.search(norm):
            return Verdict(False, rule=f"safe:{safe.pattern}", text=norm)
    for category, phrase, rx in rules.phrases:
        if rx.search(norm):
            return Verdict(True, category=category, rule=f"phrase:{phrase}", text=norm)
    return Verdict(False, text=norm)


def classify_url(url: Optional[str]) -> Verdict:
    if not url:
        return Verdict(False)
    for rx in _rules().urls:
        if rx.search(str(url)):
            return Verdict(True, category="url", rule=f"url:{rx.pattern}", text=str(url))
    return Verdict(False, text=str(url))


def classify(action: str, accessible_name: Optional[str] = None, role: Optional[str] = None,
             url: Optional[str] = None, extra_text: Iterable[str] = ()) -> Verdict:
    """
    action:          ActionEngine action name (click, navigate, verifyText, ...)
    accessible_name: visible / ARIA name of the target control
    role:            ARIA role, if known (informational; a 'link' with a destructive
                     href is caught through *url*)
    url:             navigate target or the link's href
    extra_text:      identifier-ish strings (locator key, id, test-id) — split into words
    """
    if action in NAVIGATION_ACTIONS:
        return classify_url(url)
    if action not in INTERACTION_ACTIONS:
        return Verdict(False)
    url_verdict = classify_url(url)
    if url_verdict.destructive:
        return url_verdict
    parts = [accessible_name or ""] + [words_of(t) for t in extra_text if t]
    return classify_text(" ".join(p for p in parts if p))


def _entry_text(key: Optional[str], entry: Optional[Dict[str, Any]]) -> tuple:
    """(accessible_name, role, extra_text) for a locator_map.json entry."""
    entry = entry or {}
    etype = entry.get("type")
    loc = entry.get("locator") or ""
    role = None
    name = ""
    extra = [key or ""]
    if etype == "role":
        role = loc
        name = entry.get("name") or ""
    elif etype in ("text", "label", "placeholder"):
        name = loc
    elif etype in ("testid", "css", "xpath"):
        extra.append(loc)
    return name, role, extra


def classify_step(step: Dict[str, Any], locator_map: Optional[Dict[str, Any]] = None) -> Verdict:
    """Classify one action-library plan step against the project's locator map."""
    if not isinstance(step, dict):
        return Verdict(False)
    action = step.get("action") or ""
    if action in NAVIGATION_ACTIONS:
        return classify_url(step.get("value"))
    if action not in INTERACTION_ACTIONS:
        return Verdict(False)
    if action == "pressKey" and str(step.get("value") or "").lower() not in ("enter", "numpadenter"):
        return Verdict(False)
    locator_map = locator_map or {}
    key = step.get("locator_key")
    if action == "dragAndDrop":
        key = step.get("target_locator_key") or key
    name, role, extra = _entry_text(key, locator_map.get(key) if key else None)
    if action in ("selectDropdownByText", "selectDropdownByValue"):
        # Choosing an option is destructive only if the option itself is ("Delete").
        name = f"{name} {step.get('value') or ''}".strip()
    return classify(action, accessible_name=name, role=role, url=None, extra_text=extra)
