"""
interactive_dom_scan.py — wrapper around InteractiveScanner for recording.

Called by main.py's `--record` CLI step (a human drives the browser and
this module persists what they did) and, for checkpoint recovery, by
DiscoveryAgent when a prior recording was interrupted.

Produces, under application_assets/{project}/comprehension/ (or
comprehension/modules/{module_id}/ when module_id is given):
  dom_elements.json            — multi-page element data
  dom_intents.json             — multi-page intent suggestions
  interactive/session.json     — raw click/API/transition events
  interactive/user_flows.json  — assembled user flows (confidence=0.95)
  .scan_checkpoint.json        — written mid-session for crash recovery
"""

import json
import os
from typing import Any, Dict, List, Optional

from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.discovery.dom_scan import assign_stable_locator_ids, merge_elements
from tools.discovery.paths import comprehension_scan_dir
from tools.interactive_scanner import InteractiveScanner
from tools.intent_generator import generate_intent_suggestions_multipage
from tools.state.artifact_registry import ArtifactRegistry


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"


def _page_key(page: Dict[str, Any]) -> str:
    return page.get("path") or page.get("url") or page.get("page_id") or ""


def _merge_pages(
    existing_pages: List[Dict[str, Any]], fresh_pages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Same never-delete/never-duplicate merge as merge_elements, applied per
    page (matched by path/url) instead of to one flat element list — an
    interactive scan's dom_elements.json groups elements under pages."""
    existing_by_key = {_page_key(p): p for p in existing_pages if _page_key(p)}
    fresh_by_key = {_page_key(p): p for p in fresh_pages if _page_key(p)}

    merged_pages: List[Dict[str, Any]] = []
    added: List[str] = []
    updated: List[str] = []
    possibly_removed: List[str] = []

    for page in existing_pages:
        key = _page_key(page)
        fresh = fresh_by_key.get(key)
        if fresh is None:
            merged_pages.append(page)  # kept, never deleted
            continue
        result = merge_elements(page.get("elements", []), fresh.get("elements", []))
        added += result["added"]
        updated += result["updated"]
        possibly_removed += result["possibly_removed"]
        merged_page = dict(fresh)
        merged_page["elements"] = result["elements"]
        merged_page["element_count"] = len(result["elements"])
        merged_pages.append(merged_page)

    for page in fresh_pages:
        key = _page_key(page)
        if key not in existing_by_key:
            merged_pages.append(page)
            added += [e.get("locator_id") for e in page.get("elements", []) if e.get("locator_id")]

    return {
        "pages": merged_pages,
        "added": added,
        "updated": updated,
        "possibly_removed": possibly_removed,
    }


def scan_dom_interactive(
    url: str,
    browser: str = "chromium",
    project_dir: str = "",
    resume: bool = False,
    storage_state_path: Optional[str] = None,
    auth_config: Optional[dict] = None,
    setup_steps: Optional[list] = None,
    module_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Open *url* in a live browser and let the user explore.

    *setup_steps* (and storage_state_path/auth_config) run once before the
    interactive session starts — the same module login/navigation sequence
    the non-interactive scan_dom() already runs, so a module requiring auth
    lands on its target URL logged in.

    Returns a dict with multi-page element data, session events, and user flows.
    Side-effect: writes session.json, user_flows.json, and a checkpoint under
    *project_dir*/test_comprehension/ (or test_comprehension/modules/*module_id*/ when
    *module_id* is given) when *project_dir* is provided.
    """
    comp_root = os.path.join(project_dir, "test_comprehension") if project_dir else ""
    discovery_dir = comprehension_scan_dir(comp_root, module_id) if comp_root else ""
    checkpoint_path = os.path.join(discovery_dir, ".scan_checkpoint.json") if discovery_dir else ""

    resume_data: Optional[Dict] = None
    if resume and checkpoint_path and os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                ckpt = json.load(f)
            if ckpt.get("status") == "in_progress":
                resume_data = ckpt
        except Exception:
            pass

    scanner = InteractiveScanner(browser_name=browser)
    result = scanner.scan_interactive(
        url=url,
        checkpoint_path=checkpoint_path,
        resume_data=resume_data,
        storage_state_path=storage_state_path,
        auth_config=auth_config,
        setup_steps=setup_steps,
    )

    if discovery_dir:
        os.makedirs(discovery_dir, exist_ok=True)
        _write_session_json(result, discovery_dir)
        _write_user_flows_json(result, discovery_dir)

    return {
        "elements": result.get("elements", []),
        "element_count": result.get("element_count", 0),
        "pages": result.get("pages", []),
        "total_element_count": result.get("total_element_count", 0),
        "scan_mode": "interactive",
        "_user_flows": result.get("_user_flows", []),
    }


def save_dom_scan_interactive(
    scan_data: Dict[str, Any],
    url: str,
    project_name: str,
    output_dir: str,
    module_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Persist dom_elements.json and dom_intents.json for an interactive scan result.

    Mirrors the signature of dom_scan.save_dom_scan so DiscoveryAgent can call
    the same downstream path regardless of interactive vs non-interactive mode.
    dom_elements.json is merge-written per page (see _merge_pages) for the
    same never-delete/never-duplicate reason as the non-interactive path.
    """
    os.makedirs(output_dir, exist_ok=True)

    pages = scan_data.get("pages", [])

    project_dir = os.path.dirname(os.path.normpath(output_dir))
    registry = ArtifactRegistry(project_dir)
    pages = [dict(p, elements=assign_stable_locator_ids(p.get("elements", []), module_id, registry)) for p in pages]

    elements_path = os.path.join(output_dir, "dom_elements.json")
    drift = {"added": [], "updated": [], "possibly_removed": []}
    if pages and os.path.exists(elements_path):
        try:
            with open(elements_path, encoding="utf-8") as f:
                existing_doc = json.load(f) or {}
            existing_pages = existing_doc.get("pages", [])
        except Exception:
            existing_pages = []
        merge_result = _merge_pages(existing_pages, pages)
        pages = merge_result["pages"]
        drift = {k: merge_result[k] for k in ("added", "updated", "possibly_removed")}

    elements = pages[0]["elements"] if pages else assign_stable_locator_ids(
        scan_data.get("elements", []), module_id, registry
    )

    # ── dom_elements.json ────────────────────────────────────────────
    with open(elements_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "url": url,
                "project": project_name,
                "scan_mode": "interactive",
                "total_element_count": sum(len(p.get("elements", [])) for p in pages) or len(elements),
                "elements": elements,   # backward-compat: first page elements
                "pages": pages,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    registry.save()

    if drift["added"] or drift["updated"] or drift["possibly_removed"]:
        from tools.state.review_queue import record_locator_drift
        queue_dir = os.path.join(_ASSETS_BASE, _safe_name(project_name))
        record_locator_drift(
            project_name, module_id or "_default",
            drift["added"], drift["updated"], drift["possibly_removed"],
            output_dir=queue_dir,
        )

    # ── dom_intents.json ─────────────────────────────────────────────
    if pages:
        intent_data = generate_intent_suggestions_multipage(pages)
    else:
        from tools.intent_generator import generate_intent_suggestions
        intent_data = generate_intent_suggestions(project_name, elements)

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


def promote_checkpoint(
    checkpoint_path: str,
    url: str,
    project_name: str,
    output_dir: str,
    module_id: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """
    Rebuild final interactive-scan artifacts from an interrupted/abandoned
    checkpoint, so a session that never reached scan_interactive()'s normal
    return path still produces usable output instead of nothing.

    Reuses InteractiveScanner._restore_from_checkpoint()/_finalize_current_page()/
    _build_result() — the same assembly logic a clean run uses — so the
    written files are indistinguishable from a normal recording's output.

    Returns None if there's no checkpoint, it's unreadable, or it captured
    nothing worth promoting (e.g. the session was abandoned before any page
    was ever scanned).
    """
    if not checkpoint_path or not os.path.exists(checkpoint_path):
        return None
    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            ckpt = json.load(f)
    except Exception:
        return None

    has_data = bool(
        ckpt.get("pages") or ckpt.get("all_click_events") or ckpt.get("current_page_elements")
    )
    if not has_data:
        return None

    scanner = InteractiveScanner()
    scanner._restore_from_checkpoint(ckpt)
    if scanner._current_page_elements or scanner._current_page_clicks:
        scanner._finalize_current_page(full_url=ckpt.get("base_url") or url)
    result = scanner._build_result(ckpt.get("base_url") or url)

    discovery_dir = os.path.dirname(os.path.abspath(checkpoint_path))
    _write_session_json(result, discovery_dir)
    _write_user_flows_json(result, discovery_dir)

    return save_dom_scan_interactive(
        scan_data=result,
        url=url,
        project_name=project_name,
        output_dir=output_dir,
        module_id=module_id,
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _write_session_json(result: Dict, discovery_dir: str) -> None:
    session_data = result.get("_session_data", {})
    interactive_dir = os.path.join(discovery_dir, "interactive")
    os.makedirs(interactive_dir, exist_ok=True)
    path = os.path.join(interactive_dir, "session.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)


def _write_user_flows_json(result: Dict, discovery_dir: str) -> None:
    flows = result.get("_user_flows", [])
    interactive_dir = os.path.join(discovery_dir, "interactive")
    os.makedirs(interactive_dir, exist_ok=True)
    path = os.path.join(interactive_dir, "user_flows.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"flows": flows}, f, indent=2, ensure_ascii=False)
