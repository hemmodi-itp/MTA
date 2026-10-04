"""
dom_scan.py — wraps PlaywrightScanner for the discovery phase.

Produces two artefacts under application_assets/{project}/comprehension/
(or comprehension/modules/{module_id}/ for modular projects — the caller
passes the resolved output_dir; see tools/discovery/paths.py):
  dom_elements.json  — raw element data from the page
  dom_intents.json   — intent suggestions derived from those elements
                       (already have locator_id / selector assigned)

dom_elements.json is merge-written, never overwritten wholesale: PlaywrightScanner
assigns locator_id as a bare per-scan counter (LOC-0001, LOC-0002, ...), which is
NOT stable across reruns — the same physical element can get a different id if
scan order shifts. _assign_stable_locator_ids replaces that counter with an id
derived from durable identity fields via ArtifactRegistry (same content-hash
mechanism already used for intent_id), so the same element gets the same
locator_id indefinitely. merge_elements then folds a fresh scan into whatever
dom_elements.json already exists: unchanged elements are left alone, changed
elements are updated in place, new elements are appended, and an element missing
from the fresh scan is kept (never deleted) and reported as possibly removed —
also used by interactive_dom_scan.py for the same reason.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.intent_generator import generate_intent_suggestions, generate_intent_suggestions_multipage
from tools.playwright_scanner import PlaywrightScanner
from tools.state.artifact_registry import ArtifactRegistry


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"


# ── Stable locator_id assignment + merge-on-rescan ──────────────────────────

def _element_identity_parts(element: Dict[str, Any]) -> Tuple[str, ...]:
    """Durable fields that identify the same physical element across scans —
    deliberately not positional CSS, which shifts if sibling elements are
    added/removed above it in the DOM.

    tag/role alone are NOT treated as durable: a page can have any number of
    same-tag, same-role elements (e.g. six unlabeled icon <button>s), and
    tag+role alone can't tell them apart — that collision is exactly what
    silently merged 6 distinct buttons (mic, TTS toggle, avatar footer x2,
    input menu, side-nav toggle) onto one locator_id on a real project. At
    least one of id/name/testid/aria_label/display_text must be present for
    tag/role to be trusted as part of the identity; otherwise CSS position is
    the only remaining distinguisher."""
    sem = element.get("semantic_locators") or {}
    attr = element.get("attribute_locators") or {}
    tag = element.get("tag") or ""
    role = sem.get("role") or ""
    durable_signal = (
        attr.get("id") or attr.get("name") or attr.get("testid")
        or sem.get("aria_label") or element.get("display_text") or ""
    )
    if durable_signal:
        return (
            tag, role,
            attr.get("id") or "", attr.get("name") or "", attr.get("testid") or "",
            sem.get("aria_label") or "", element.get("display_text") or "",
        )
    # Nothing durable to identify by — fall back to technical CSS. Not
    # guaranteed stable across DOM changes, but deterministic for this element,
    # and strictly better than colliding every anonymous same-tag/role element
    # onto a single identity.
    css = ((element.get("technical_locators") or {}).get("css")) or ""
    return (tag, role, css)


def assign_stable_locator_ids(
    elements: List[Dict[str, Any]], module_id: Optional[str], registry: ArtifactRegistry
) -> List[Dict[str, Any]]:
    """Replace each element's locator_id (PlaywrightScanner's bare per-scan
    counter) with one derived from ArtifactRegistry's content-hash mechanism —
    the same physical element gets the same LOC-XXXX id across reruns."""
    stamped = []
    for element in elements:
        parts = _element_identity_parts(element)
        artifact_id, _is_new, _hash = registry.get_or_create_id(module_id or "GEN", "LOC", *parts)
        n = int(artifact_id.rsplit("_", 1)[-1])
        new_element = dict(element)
        new_element["locator_id"] = f"LOC-{n:04d}"
        stamped.append(new_element)
    return stamped


_MERGE_COMPARE_FIELDS = (
    "tag", "display_text", "semantic_locators", "attribute_locators",
    "playwright_locators", "technical_locators", "recommended_locator",
    "locator_candidates", "quality", "intent_hints",
)


def _elements_content_equal(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return all(a.get(f) == b.get(f) for f in _MERGE_COMPARE_FIELDS)


def merge_elements(
    existing_elements: List[Dict[str, Any]],
    fresh_elements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Merge a freshly-scanned element list (already stamped with stable
    locator_ids via assign_stable_locator_ids) into a prior scan's element
    list. Never deletes: an existing element whose id no longer appears in
    the fresh scan is kept as-is and reported as possibly removed rather than
    dropped. Never duplicates: matching is by locator_id, so the same element
    rescanned updates its existing entry in place instead of appending a
    second copy.

    Returns {"elements": [...], "added": [locator_id, ...],
             "updated": [locator_id, ...], "possibly_removed": [locator_id, ...]}.
    """
    fresh_by_id = {e.get("locator_id"): e for e in fresh_elements if e.get("locator_id")}
    existing_ids = {e.get("locator_id") for e in existing_elements if e.get("locator_id")}

    merged: List[Dict[str, Any]] = []
    updated: List[str] = []

    for element in existing_elements:
        loc_id = element.get("locator_id")
        fresh = fresh_by_id.get(loc_id)
        if fresh is None:
            merged.append(element)  # kept, never deleted
            continue
        if _elements_content_equal(element, fresh):
            merged.append(element)
        else:
            merged.append(fresh)
            updated.append(loc_id)

    added: List[str] = []
    for element in fresh_elements:
        loc_id = element.get("locator_id")
        if loc_id not in existing_ids:
            merged.append(element)
            added.append(loc_id)

    possibly_removed = [loc_id for loc_id in existing_ids if loc_id not in fresh_by_id]

    return {"elements": merged, "added": added, "updated": updated, "possibly_removed": possibly_removed}


def scan_dom(
    url: str,
    browser: str = "chromium",
    headless: bool = True,
    storage_state_path: str = None,
    auth_config: dict = None,
    setup_steps: list = None,
    checkpoint_path: str = None,
) -> Dict[str, Any]:
    """
    Open *url* with Playwright and return raw scan data.

    Args:
        storage_state_path: Path to a Playwright storageState JSON file
                            (cookies + localStorage). When provided, the browser
                            context is pre-authenticated — useful for SSO/login-
                            protected URLs.
        auth_config: Full auth: block from project.yaml. When strategy is
                     "live_login", the browser performs a real login before
                     navigating to *url* — no state file required.
        checkpoint_path: If set, elements collected so far are periodically
                         flushed to this path — lets a caller-side timeout
                         that abandons this call still promote partial data.

    Returns:
        {
            "elements": [...],   # raw element dicts from PlaywrightScanner
            "element_count": N,
        }
    """
    runner = PlaywrightScanner(browser_name=browser, headless=headless)
    if setup_steps:
        runner.logger.info(f"  scan_dom received {len(setup_steps)} setup step(s) — will execute before navigating to target")
    result = runner.scan_page(
        url,
        storage_state_path=storage_state_path,
        auth_config=auth_config,
        setup_steps=setup_steps,
        checkpoint_path=checkpoint_path,
    )
    return {
        "elements": result.get("elements", []),
        "element_count": len(result.get("elements", [])),
    }


def save_dom_scan(
    scan_data: Dict[str, Any],
    url: str,
    project_name: str,
    output_dir: str,
    module_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Persist dom_elements.json and dom_intents.json under *output_dir*.

    dom_elements.json is merge-written: locator_ids are stabilized via
    ArtifactRegistry, then folded into any existing file at this path so a
    rescan never deletes or duplicates an element — see module docstring.

    Returns mapping of {"dom_elements": path, "dom_intents": path}.
    """
    os.makedirs(output_dir, exist_ok=True)

    elements: List[Dict] = scan_data.get("elements", [])
    pages: List[Dict] = scan_data.get("pages", [])
    is_multipage = bool(pages)

    # project_dir is the parent of output_dir (application_assets/{project}/discovery,
    # or .../comprehension/modules/ for modular projects — either way this is the
    # scope ArtifactRegistry namespaces by module_id internally, so it's correct
    # for both layouts even though it isn't always the true project root).
    project_dir = os.path.dirname(os.path.normpath(output_dir))
    registry = ArtifactRegistry(project_dir)

    elements = assign_stable_locator_ids(elements, module_id, registry)

    elements_path = os.path.join(output_dir, "dom_elements.json")
    drift = {"added": [], "updated": [], "possibly_removed": []}
    if not is_multipage and os.path.exists(elements_path):
        try:
            with open(elements_path, encoding="utf-8") as f:
                existing_doc = json.load(f) or {}
            existing_elements = existing_doc.get("elements", [])
        except Exception:
            existing_elements = []
        merge_result = merge_elements(existing_elements, elements)
        elements = merge_result["elements"]
        drift = {k: merge_result[k] for k in ("added", "updated", "possibly_removed")}

    # ── raw elements ────────────────────────────────────────────────────
    elements_doc: dict = {"url": url, "project": project_name, "elements": elements}
    if is_multipage:
        elements_doc["scan_mode"] = "interactive"
        elements_doc["total_element_count"] = scan_data.get("total_element_count", len(elements))
        elements_doc["pages"] = pages
    with open(elements_path, "w", encoding="utf-8") as f:
        json.dump(elements_doc, f, indent=2, ensure_ascii=False)

    if drift["added"] or drift["updated"] or drift["possibly_removed"]:
        from tools.state.review_queue import record_locator_drift
        queue_dir = os.path.join(_ASSETS_BASE, _safe_name(project_name))
        record_locator_drift(
            project_name, module_id or "_default",
            drift["added"], drift["updated"], drift["possibly_removed"],
            output_dir=queue_dir,
        )

    # ── intent suggestions ───────────────────────────────────────────────
    if is_multipage:
        intent_data = generate_intent_suggestions_multipage(pages, registry=registry)
    else:
        intent_data = generate_intent_suggestions(project_name, elements, registry=registry)
    registry.save()
    intents_path = os.path.join(output_dir, "dom_intents.json")
    with open(intents_path, "w", encoding="utf-8") as f:
        json.dump(
            {"url": url, "project": project_name, **intent_data},
            f,
            indent=2,
            ensure_ascii=False,
        )

    return {
        "dom_elements": elements_path,
        "dom_intents": intents_path,
    }
