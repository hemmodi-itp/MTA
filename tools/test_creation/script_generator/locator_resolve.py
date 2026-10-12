"""
locator_resolve.py — Python mirror of LocatorManager.ts's resolve(): a locator_map.json entry
-> a Playwright Locator, for live dry-run validation.

Shared by ScriptGenerationAgent (pre-generation locator validation) and HealingAgent
(post-repair check); both used to carry identical private copies.

Entry shape:
    {type, locator, name?}                       — unchanged since Phase 0
    + frame?: ["iframe#pay", ...]                — Phase 2: frameLocator chain from the page
    + scope?: {type, locator, name?}             — Phase 2: resolve the entry inside this container

Phase 4: `testid` entries use the project's `execution.test_id_attribute` — the same attribute the TS
runtime's getByTestId uses (playwright.config.ts testIdAttribute). Python Playwright's own default is
data-testid, so before Phase 4 a data-test project's testid keys were validated against the wrong attribute.

Rules kept from the original copies (do not change without changing both callers' contract):
  * a key passes only when it resolves to exactly ONE element (count() == 1) — a 2+ match is a
    Playwright strict-mode violation at run time;
  * an unknown type, or any resolution error, is "can't tell" -> treated as resolving (fail-open).
"""

from typing import Any, Optional

KNOWN_TYPES = ("css", "xpath", "role", "text", "label", "testid", "placeholder")


class UnknownLocatorType(ValueError):
    pass


def by_test_id(base: Any, value: str, attribute: Optional[str] = None):
    """getByTestId with a configurable attribute. data-testid (or None) keeps get_by_test_id; any other
    attribute is the equivalent exact attribute selector (CSS pierces open shadow roots like getByTestId)."""
    if not attribute or attribute == "data-testid":
        return base.get_by_test_id(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return base.locator(f'[{attribute}="{escaped}"]')


def _on(base: Any, t: Optional[str], v: str, name: Optional[str], test_id_attribute: Optional[str] = None):
    if t == "css":
        return base.locator(v)
    if t == "xpath":
        return base.locator(f"xpath={v}")
    if t == "role":
        return base.get_by_role(v, name=name) if name else base.get_by_role(v)
    if t == "text":
        return base.get_by_text(v)
    if t == "label":
        return base.get_by_label(v)
    if t == "testid":
        return by_test_id(base, v, test_id_attribute)
    if t == "placeholder":
        return base.get_by_placeholder(v)
    raise UnknownLocatorType(str(t))


def resolve_entry(page: Any, entry: dict, test_id_attribute: Optional[str] = None):
    """Build the Locator (raises UnknownLocatorType for an unknown entry or scope type)."""
    base: Any = page
    for sel in entry.get("frame") or []:
        base = base.frame_locator(sel)
    scope = entry.get("scope")
    if isinstance(scope, dict) and scope:
        base = _on(base, scope.get("type"), scope.get("locator", ""), scope.get("name"), test_id_attribute)
    return _on(base, entry.get("type"), entry.get("locator", ""), entry.get("name"), test_id_attribute)


def entry_resolves(page: Any, entry: dict, test_id_attribute: Optional[str] = None) -> bool:
    try:
        locator = resolve_entry(page, entry, test_id_attribute)
    except UnknownLocatorType:
        return True  # unknown type — can't check, don't reject
    except Exception:
        return True  # a resolution error is "can't tell", not a rejection
    try:
        # Exactly 1, not just >0: a locator matching 2+ elements (e.g. two "Sign in" buttons —
        # one text, one icon, shown responsively) is a strict-mode violation at run time.
        return locator.count() == 1
    except Exception:
        return True
