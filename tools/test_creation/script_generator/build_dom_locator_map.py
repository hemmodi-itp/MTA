"""
build_dom_locator_map.py — extract the best Playwright expression for every
DOM element in dom_elements.json, ranked by locator stability.

Priority order (highest to lowest stability):
  1. playwright_locators.get_by_placeholder  → page.getByPlaceholder("...")
  2. playwright_locators.get_by_role         → page.getByRole("role", { name: "..." })
  3. playwright_locators.get_by_text         → page.getByText("...")
  4. recommended_locator type=id             → page.locator("#id")
  5. recommended_locator type=name           → page.locator('[name="..."]')
  6. recommended_locator type=css            → page.locator("css")
  7. technical_locators.css                  → page.locator("css")  [fragile]
  8. No locator found                        → None (LLM must use test.skip)

Usage:
    from tools.test_creation.script_generator.build_dom_locator_map import build_locator_map
    loc_map = build_locator_map(dom_elements_path)
    # Returns: {"LOC-0002": "page.getByPlaceholder('Search Products ...')", ...}
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Optional, Tuple


def build_locator_map(dom_elements_path: str) -> Dict[str, str]:
    """
    Read dom_elements.json and return {locator_id: playwright_expression}.

    The returned expression is already a valid TypeScript snippet that can be
    embedded directly in a .spec.ts file, e.g.:

        "page.getByPlaceholder('Search Products ...')"

    Elements with no resolvable locator are not included in the map.
    """
    if not os.path.exists(dom_elements_path):
        return {}

    with open(dom_elements_path, encoding="utf-8") as f:
        raw = json.load(f)

    # Support both flat list and multi-page interactive scan format
    if isinstance(raw, dict) and raw.get("pages"):
        elements: List[dict] = [
            el
            for page in raw["pages"]
            for el in page.get("elements", [])
        ]
    elif isinstance(raw, dict):
        elements = raw.get("elements", [])
    else:
        elements = raw if isinstance(raw, list) else []

    result: Dict[str, str] = {}
    for el in elements:
        loc_id = el.get("locator_id")
        if not loc_id:
            continue
        expr = _best_playwright_expr(el)
        if expr:
            result[loc_id] = expr

    return result


def get_playwright_expr(element: dict) -> Optional[str]:
    """Return the best Playwright expression for a single element, or None."""
    return _best_playwright_expr(element)


# ── Priority resolution ────────────────────────────────────────────────────────

def _best_playwright_expr(el: dict) -> Optional[str]:
    pw = el.get("playwright_locators") or {}

    # Priority 1: getByPlaceholder
    if pw.get("get_by_placeholder"):
        ph = (pw["get_by_placeholder"] or {}).get("placeholder", "")
        if ph:
            return f"page.getByPlaceholder({_quote(ph)})"

    # Priority 2: getByRole
    if pw.get("get_by_role"):
        role_cfg = pw["get_by_role"] or {}
        role = role_cfg.get("role", "")
        name = role_cfg.get("name", "")
        if role and name:
            return f"page.getByRole({_quote(role)}, {{ name: {_quote(name)} }})"
        if role:
            return f"page.getByRole({_quote(role)})"

    # Priority 3: getByText
    if pw.get("get_by_text"):
        text = (pw["get_by_text"] or {}).get("text", "")
        if text:
            return f"page.getByText({_quote(text)})"

    # Priority 4-6: recommended_locator
    rec = el.get("recommended_locator") or {}
    t = rec.get("type", "")
    v = rec.get("value") or {}

    if t == "id" and v.get("id"):
        return f"page.locator({_quote('#' + v['id'])})"

    if t == "name" and v.get("name"):
        name_selector = '[name="' + v["name"] + '"]'
        return f"page.locator({_quote(name_selector)})"

    if t == "placeholder" and v.get("placeholder"):
        return f"page.getByPlaceholder({_quote(v['placeholder'])})"

    if t == "css" and v.get("css"):
        return f"page.locator({_quote(v['css'])})"

    if t == "testid" and v.get("testid"):
        return f"page.getByTestId({_quote(v['testid'])})"

    # Priority 7: technical CSS (last resort — fragile positional selector)
    css = (el.get("technical_locators") or {}).get("css", "")
    if css:
        return f"page.locator({_quote(css)})"

    return None


def _quote(s: str) -> str:
    """Wrap in single quotes, escaping any embedded single quotes."""
    return "'" + s.replace("'", "\\'") + "'"


# ── Snapshot helper ────────────────────────────────────────────────────────────

def build_element_summary(dom_elements_path: str) -> List[Dict[str, str]]:
    """
    Return a compact list of {locator_id, playwright_expr, description, tag}
    suitable for injecting into LLM prompts.

    Only elements with a resolvable Playwright expression are included.
    """
    if not os.path.exists(dom_elements_path):
        return []

    with open(dom_elements_path, encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and raw.get("pages"):
        elements = [el for page in raw["pages"] for el in page.get("elements", [])]
    elif isinstance(raw, dict):
        elements = raw.get("elements", [])
    else:
        elements = raw if isinstance(raw, list) else []

    summaries = []
    for el in elements:
        expr = _best_playwright_expr(el)
        if not expr:
            continue
        summaries.append({
            "locator_id": el.get("locator_id", ""),
            "playwright_expr": expr,
            "tag": el.get("tag", ""),
            "description": el.get("description", el.get("text_content", "")),
            "placeholder": el.get("placeholder", ""),
            "aria_label": el.get("aria_label", ""),
        })
    return summaries


# ── Named locator map (action-library generation) ──────────────────────────
#
# A structured, keyed equivalent of _best_playwright_expr, consumed by the
# TypeScript LocatorManager at test-run time instead of a raw expression
# string baked into generated code. One flat, project-wide locator_map.json
# merges every module's dom_elements.json — never overwritten wholesale, see
# build_named_locator_map's merge algorithm below.

def _extract_elements(dom_elements_path: str) -> List[dict]:
    if not os.path.exists(dom_elements_path):
        return []

    with open(dom_elements_path, encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and raw.get("pages"):
        return [el for page in raw["pages"] for el in page.get("elements", [])]
    if isinstance(raw, dict):
        return raw.get("elements", [])
    return raw if isinstance(raw, list) else []


def _discover_modules(comprehension_dir: str) -> List[Tuple[str, str]]:
    """Return [(module_id, dom_elements_path), ...]. Per-module layout
    (comprehension_dir/modules/{module_id}/dom_elements.json, e.g. AWS_Test)
    if present, else the flat single-file layout (e.g. sauceLabs) tagged
    module_id="_default"."""
    modules_root = os.path.join(comprehension_dir, "modules")
    if os.path.isdir(modules_root):
        result = []
        for name in sorted(os.listdir(modules_root)):
            module_dir = os.path.join(modules_root, name)
            dom_path = os.path.join(module_dir, "dom_elements.json")
            if os.path.isdir(module_dir) and os.path.exists(dom_path):
                result.append((name, dom_path))
        return result
    flat_path = os.path.join(comprehension_dir, "dom_elements.json")
    if os.path.exists(flat_path):
        return [("_default", flat_path)]
    return []


def _dom_elements_path_for_module(comprehension_dir: str, module_id: Optional[str]) -> Optional[str]:
    if module_id and module_id != "_default":
        path = os.path.join(comprehension_dir, "modules", module_id, "dom_elements.json")
        return path if os.path.exists(path) else None
    path = os.path.join(comprehension_dir, "dom_elements.json")
    return path if os.path.exists(path) else None


def _best_locator_entry(el: dict) -> Optional[dict]:
    """Same priority chain as _best_playwright_expr, extended to reach every
    LocatorEntry.type LocatorManager.ts supports (adds label, xpath):
    placeholder > role > label > text > id > name > css > testid >
    technical css > technical xpath (absolute last resort)."""
    pw = el.get("playwright_locators") or {}

    if pw.get("get_by_placeholder"):
        ph = (pw["get_by_placeholder"] or {}).get("placeholder", "")
        if ph:
            return {"type": "placeholder", "locator": ph}

    if pw.get("get_by_role"):
        role_cfg = pw["get_by_role"] or {}
        role = role_cfg.get("role", "")
        name = role_cfg.get("name", "")
        if role and name:
            return {"type": "role", "locator": role, "name": name}
        if role:
            return {"type": "role", "locator": role}

    if pw.get("get_by_label"):
        label = (pw["get_by_label"] or {}).get("label", "")
        if label:
            return {"type": "label", "locator": label}

    if pw.get("get_by_text"):
        text = (pw["get_by_text"] or {}).get("text", "")
        if text:
            return {"type": "text", "locator": text}

    rec = el.get("recommended_locator") or {}
    t = rec.get("type", "")
    v = rec.get("value") or {}

    if t == "id" and v.get("id"):
        return {"type": "css", "locator": "#" + v["id"]}

    if t == "name" and v.get("name"):
        return {"type": "css", "locator": '[name="' + v["name"] + '"]'}

    if t == "placeholder" and v.get("placeholder"):
        return {"type": "placeholder", "locator": v["placeholder"]}

    if t == "css" and v.get("css"):
        return {"type": "css", "locator": v["css"]}

    if t == "testid" and v.get("testid"):
        return {"type": "testid", "locator": v["testid"]}

    css = (el.get("technical_locators") or {}).get("css", "")
    if css:
        return {"type": "css", "locator": css}

    xpath = (el.get("technical_locators") or {}).get("xpath", "")
    if xpath:
        return {"type": "xpath", "locator": xpath}

    return None


def _locator_value_key(entry: dict) -> Tuple[str, str, str]:
    """A hashable fingerprint of the resolved locator itself (ignoring key
    name/description) — used to detect the same element re-appearing under a
    new id instead of minting a duplicate key for an identical locator."""
    return (entry.get("type") or "", entry.get("locator") or "", entry.get("name") or "")


def _locator_fields_equal(a: dict, b: dict) -> bool:
    return _locator_value_key(a) == _locator_value_key(b)


def _apply_locator_update(existing_entry: dict, new_entry: dict, loc_id: str, module_id: str) -> dict:
    """Update an existing locator_map entry's resolved locator in place,
    preserving its key, description, and any other human-added fields.
    Clears a stale `name` (role-type only) when the new locator type doesn't
    carry one, rather than leaving it dangling from a prior role-type entry."""
    merged = dict(existing_entry)
    merged.pop("name", None)
    merged.update(new_entry)
    merged["_source_locator_id"] = loc_id
    merged["_module_id"] = module_id
    return merged


def _slugify(s: str, max_len: int = 50) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("_", 1)[0]
    return slug


def _mint_key(el: dict, used_keys: set) -> str:
    intent_hints = el.get("intent_hints") or []
    display_text = el.get("display_text") or ""
    locator_id = el.get("locator_id", "")
    tag = el.get("tag", "el")

    if intent_hints and _slugify(intent_hints[0]):
        base = _slugify(intent_hints[0])
    elif display_text and _slugify(display_text):
        base = _slugify(display_text)
    else:
        base = f"{tag}_{locator_id.lower().replace('-', '_')}"

    if not base:
        base = f"{tag}_{locator_id.lower().replace('-', '_')}"

    key = base
    n = 2
    while key in used_keys:
        key = f"{base}_{n}"
        n += 1

    used_keys.add(key)
    return key


def build_named_locator_map(
    comprehension_dir: str,
    existing_map: Optional[Dict[str, dict]] = None,
    llm_reconcile: Optional[Callable[[List[dict], List[dict]], Dict[str, str]]] = None,
) -> Dict[str, object]:
    """
    Merge every module's dom_elements.json under *comprehension_dir* into one
    flat, project-wide locator map — never deleting or duplicating an
    existing key on rescan.

    Merge algorithm:
      1. An element whose stable locator_id matches an existing entry's
         _source_locator_id: identical computed locator leaves the entry
         untouched; a changed locator updates it in place, same key.
      2. An unmatched element whose computed locator is byte-identical to an
         existing entry's is treated as that same element re-appearing under
         a new id — reuses the existing key instead of minting a duplicate.
      3. Any remaining unmatched new elements, together with existing entries
         whose source element no longer appears in the scan, are handed to
         *llm_reconcile* (if given) to decide "same element, different
         locator" (reuse the key) vs "genuinely new"/"genuinely removed".
         Runs only on this ambiguous remainder, not on every element.
      4. Existing entries confirmed gone are kept — never deleted — and
         reported as possibly_removed.

    Returns {"map": {key: entry}, "added": [key, ...], "updated": [key, ...],
    "possibly_removed": [key, ...]} — the last three for record_locator_drift.
    """
    existing_map = dict(existing_map or {})
    result_map = dict(existing_map)
    used_keys = set(existing_map.keys())

    existing_by_source_id = {
        entry.get("_source_locator_id"): key
        for key, entry in existing_map.items()
        if entry.get("_source_locator_id")
    }
    existing_by_locator_value = {
        _locator_value_key(entry): key for key, entry in existing_map.items()
    }

    added: List[str] = []
    updated: List[str] = []
    claimed_existing_keys: set = set()
    unmatched_new: List[Tuple[str, dict, dict]] = []

    for module_id, dom_elements_path in _discover_modules(comprehension_dir):
        for el in _extract_elements(dom_elements_path):
            entry = _best_locator_entry(el)
            if not entry:
                continue
            loc_id = el.get("locator_id", "")

            source_key = existing_by_source_id.get(loc_id)
            if source_key:
                claimed_existing_keys.add(source_key)
                if not _locator_fields_equal(result_map[source_key], entry):
                    result_map[source_key] = _apply_locator_update(
                        result_map[source_key], entry, loc_id, module_id
                    )
                    updated.append(source_key)
                continue

            value_key = _locator_value_key(entry)
            dup_key = existing_by_locator_value.get(value_key)
            if dup_key and dup_key not in claimed_existing_keys:
                claimed_existing_keys.add(dup_key)
                result_map[dup_key] = _apply_locator_update(
                    result_map[dup_key], entry, loc_id, module_id
                )
                updated.append(dup_key)
                continue

            unmatched_new.append((module_id, el, entry))

    removed_candidates = [
        {**result_map[key], "_key": key}
        for key in existing_map
        if key not in claimed_existing_keys
    ]

    reused_by_loc_id: Dict[str, str] = {}
    if unmatched_new and removed_candidates and llm_reconcile:
        try:
            reused_by_loc_id = llm_reconcile(
                [el for _m, el, _e in unmatched_new], removed_candidates
            ) or {}
        except Exception:
            reused_by_loc_id = {}

    for module_id, el, entry in unmatched_new:
        loc_id = el.get("locator_id", "")
        reused_key = reused_by_loc_id.get(loc_id)
        if reused_key and reused_key in result_map and reused_key not in claimed_existing_keys:
            claimed_existing_keys.add(reused_key)
            result_map[reused_key] = _apply_locator_update(
                result_map[reused_key], entry, loc_id, module_id
            )
            updated.append(reused_key)
            continue

        key = _mint_key(el, used_keys)
        result_map[key] = {
            **entry,
            "description": el.get("display_text", ""),
            "_source_locator_id": loc_id,
            "_module_id": module_id,
        }
        added.append(key)

    possibly_removed = [key for key in existing_map if key not in claimed_existing_keys]

    return {"map": result_map, "added": added, "updated": updated, "possibly_removed": possibly_removed}


def write_named_locator_map(
    comprehension_dir: str,
    output_path: str,
    llm_reconcile: Optional[Callable[[List[dict], List[dict]], Dict[str, str]]] = None,
) -> Dict[str, List[str]]:
    """Build/merge the named locator map and write it to output_path as JSON.
    Returns {"added": [...], "updated": [...], "possibly_removed": [...]} for
    record_locator_drift — all empty on a project's first-ever build."""
    existing_map: Dict[str, dict] = {}
    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            existing_map = json.load(f) or {}

    result = build_named_locator_map(comprehension_dir, existing_map, llm_reconcile)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result["map"], f, indent=2)

    return {k: result[k] for k in ("added", "updated", "possibly_removed")}


def repair_named_locator(locator_map_path: str, comprehension_dir: str, key: str) -> bool:
    """
    Re-derive one locator_map.json entry from a freshly re-read dom_elements.json
    — the entry's _module_id says which module's file to re-scan. Matches via
    the entry's stored _source_locator_id first; if that id no longer exists
    (the element was removed/regenerated), falls back to a unique display_text
    match within that module. Overwrites only type/locator/name for that key —
    the key itself and its description are left untouched. Returns False if no
    confident match is found. This is HealingAgent's fix for a locator_key
    that fails live resolution — it patches this one shared entry instead of
    any .spec.ts file, so every spec using the key is fixed at once.
    """
    if not os.path.exists(locator_map_path):
        return False

    with open(locator_map_path, encoding="utf-8") as f:
        locator_map = json.load(f)

    entry = locator_map.get(key)
    if not entry:
        return False

    dom_elements_path = _dom_elements_path_for_module(comprehension_dir, entry.get("_module_id"))
    if not dom_elements_path:
        return False

    elements = _extract_elements(dom_elements_path)
    source_id = entry.get("_source_locator_id", "")

    match = next((el for el in elements if el.get("locator_id") == source_id), None)

    if match is None:
        description = (entry.get("description") or "").strip().lower()
        candidates = [
            el for el in elements
            if (el.get("display_text") or "").strip().lower() == description
        ] if description else []
        if len(candidates) == 1:
            match = candidates[0]
            entry["_source_locator_id"] = match.get("locator_id", "")

    if match is None:
        return False

    new_entry = _best_locator_entry(match)
    if not new_entry:
        return False

    entry.pop("name", None)
    entry.update(new_entry)
    locator_map[key] = entry

    with open(locator_map_path, "w", encoding="utf-8") as f:
        json.dump(locator_map, f, indent=2)

    return True


# ── Page-factory class generation (test_creation/pages.ts) ─────────────────
#
# One exported class per module (deterministic, no LLM), plus a PAGE_REGISTRY
# mapping module_id -> class, all in a single generated file — see the plan's
# "File consolidation" section for why this isn't one file per module.

def _page_class_name(module_id: str, module_name: Optional[str]) -> str:
    base = module_name or module_id
    words = re.split(r"[^A-Za-z0-9]+", base)
    class_name = "".join(w.capitalize() for w in words if w) or "Module"
    if not class_name.endswith("Page"):
        class_name += "Page"
    return class_name


def _property_name(key: str) -> str:
    """Property name for a Page class getter — the locator_map.json key,
    verbatim. Must match exactly what ActionEngine looks up
    (`this.pageObject[locator_key]`); camelCasing it here would silently
    break every generated spec's action.<verb>(locator_key, ...) call, since
    the plan/spec always carries the raw key, never a transformed one. Only
    guards the (rare, since _mint_key already restricts to [a-z0-9_]) case
    of a key that isn't a valid bare identifier."""
    if re.match(r"^[A-Za-z_]\w*$", key):
        return key
    return "_" + re.sub(r"\W", "_", key)


def render_pages_module(
    locator_map: Dict[str, dict], module_names: Optional[Dict[str, str]] = None
) -> str:
    """Render test_creation/pages.ts's full contents from locator_map.json."""
    module_names = module_names or {}
    by_module: Dict[str, List[Tuple[str, dict]]] = {}
    for key, entry in locator_map.items():
        module_id = entry.get("_module_id") or "_default"
        by_module.setdefault(module_id, []).append((key, entry))

    lines = [
        "// AUTO-GENERATED from locator_map.json — do not hand-edit.",
        "// To fix a locator: edit locator_map.json (or rerun discovery), then regenerate this file.",
        "import { Page, Locator } from '@playwright/test';",
        # pages.ts always lives at test_creation/pages.ts under a project
        # dir (application_assets/projects/{name}/test_creation/) — 3 levels
        # up reaches application_assets/_shared/runtime.
        "import { LocatorManager } from '../../../_shared/runtime/LocatorManager';",
        "",
    ]

    class_names: Dict[str, str] = {}
    for module_id in sorted(by_module):
        class_name = _page_class_name(module_id, module_names.get(module_id))
        # Keys already collide-checked project-wide by _mint_key, but two
        # modules could still independently earn the same class name — dedupe.
        base_class_name = class_name
        n = 2
        while class_name in class_names.values():
            class_name = f"{base_class_name}{n}"
            n += 1
        class_names[module_id] = class_name

        lines.append(f"export class {class_name} {{")
        lines.append("  constructor(private readonly page: Page) {}")
        lines.append("")
        for key, _entry in sorted(by_module[module_id]):
            prop = _property_name(key)
            lines.append(
                f"  get {prop}(): Locator {{ return LocatorManager.resolve(this.page, {json.dumps(key)}); }}"
            )
        lines.append("}")
        lines.append("")

    lines.append(
        "export const PAGE_REGISTRY: Record<string, new (page: Page) => Record<string, unknown>> = {"
    )
    for module_id, class_name in class_names.items():
        lines.append(f"  {json.dumps(module_id)}: {class_name},")
    lines.append("};")
    lines.append("")

    return "\n".join(lines)


def write_pages_module(
    locator_map: Dict[str, dict], output_path: str, module_names: Optional[Dict[str, str]] = None
) -> str:
    content = render_pages_module(locator_map, module_names)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
