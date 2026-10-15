"""
locators.py — make the fields of crawled forms addressable by ScriptGeneration (design note D4).

Only module landing pages reach locator_map.json through the DOM scan, so a case on /products/{id} or /cart had no
locator key to use (Phase 2 open issue #10: ACs uncovered with `missing_locator`). For every form a selected case
targets, each field and the submit button gets a locator_map entry:

    {type, locator, name, description, _module_id, _source: "form_model", _page_url, _form_id}

An entry with the same locator in the same module is reused (never duplicated); an existing key is never
overwritten. ScriptGeneration validates `_page_url` entries live on that page instead of the module page.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from tools.test_design.inputs import DesignInputs, Form

SUBMIT = "__submit__"


def _slug(s: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return slug[:max_len].rstrip("_") or "field"


def _value_key(entry: Dict[str, Any]) -> Tuple[Any, ...]:
    """Module + the DOM builder's own locator fingerprint (type, locator, name, scope, frame): a dialog-scoped
    "Save" and a page-level "Save" are different elements and never share a key."""
    from tools.test_creation.script_generator.build_dom_locator_map import _locator_value_key
    return (entry.get("_module_id") or "_default",) + tuple(_locator_value_key(entry))


_CSS_SAFE = re.compile(r"^[A-Za-z][\w-]*$")
ERROR = "__error__"


def _css_attr(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def error_container(form: Form) -> Optional[str]:
    """The CSS of the element the app showed its validation errors in (most frequent across the probes)."""
    counts: Dict[str, int] = {}
    for p in form.probes:
        for e in p.get("visible_errors") or []:
            c = e.get("container")
            if c:
                counts[c] = counts.get(c, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if counts else None


def _entries_for(form: Form, module_id: Optional[str]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Locators for a form's fields, submit button and error area.

    Fields use `#<form id> [name="<field>"]` when the form has an id: the role/name locators recorded by the
    crawl can be wrong for some widgets (a `type=search` input is role `searchbox`, not `textbox`; a <select>'s
    accessible name is its label, not its option text), and a form-scoped name attribute is unique and stable.
    The error area (CSS seen in the probes' visible errors) only exists after a submit, so it is marked
    `_dynamic` and is not live-validated on page load."""
    out = []
    scoped = bool(form.dom_id and _CSS_SAFE.match(form.dom_id))
    for fld in form.fields:
        loc = fld.locator or {}
        label = (fld.label or fld.name).splitlines()[0]
        if scoped and fld.name:
            entry: Dict[str, Any] = {"type": "css", "locator": f'#{form.dom_id} [name="{_css_attr(fld.name)}"]'}
            if loc.get("frame") is not None:
                entry["frame"] = loc["frame"]
        elif loc.get("type"):
            entry = {"type": loc["type"], "locator": loc.get("locator")}
            for extra in ("name", "scope", "frame"):      # Phase 2 locators may be container- or frame-scoped
                if loc.get(extra) is not None:
                    entry[extra] = loc[extra]
        else:
            continue
        out.append((fld.name, label, entry))
    text = (form.submit or {}).get("text")
    if text:
        submit = ({"type": "css", "locator": f'#{form.dom_id} [type="submit"]'} if scoped
                  else {"type": "role", "locator": "button", "name": text})
        out.append((SUBMIT, f"{text} button", submit))
    container = error_container(form)
    if container:
        out.append((ERROR, f"{form.dom_id or 'form'} errors", {"type": "css", "locator": container, "_dynamic": True}))
    for name, label, entry in out:
        entry.update({"description": f"{label} ({form.dom_id or 'form'} on {form.url_template})",
                      "_module_id": module_id, "_source": "form_model", "_page_url": form.sample_url,
                      "_form_id": form.form_id})
    return out


def merge_form_locators(locator_map: Dict[str, Dict[str, Any]], inp: DesignInputs,
                        cases: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Returns (new map, added keys) and sets case["locator_keys"] = {field|"submit": key} in place."""
    result = dict(locator_map)
    by_value = {_value_key(e): k for k, e in result.items()}
    forms = {f.form_id: f for f in inp.forms}
    added: List[str] = []
    keys_for: Dict[Tuple[str, str], Dict[str, str]] = {}
    for case in sorted(cases, key=lambda c: c["id"]):
        t = case.get("target") or {}
        form = forms.get(t.get("form_id") or "")
        module = case.get("module_id")
        if form is None:
            continue
        cache_key = (form.form_id, module or "")
        if cache_key not in keys_for:
            mapping: Dict[str, str] = {}
            for fname, label, entry in _entries_for(form, module):
                existing = by_value.get(_value_key(entry))
                if existing:
                    mapping[fname] = existing
                    continue
                base = _slug(label if fname != SUBMIT else f"{label}")
                key, n = base, 2
                while key in result:
                    key = f"{base}_{n}"
                    n += 1
                result[key] = entry
                by_value[_value_key(entry)] = key
                mapping[fname] = key
                added.append(key)
            keys_for[cache_key] = mapping
        mapping = keys_for[cache_key]
        names = {SUBMIT: "submit", ERROR: "error"}
        case["locator_keys"] = {names.get(k, k): v for k, v in sorted(mapping.items())}
    return result, added


def _trigger_entry(elements: List[Dict[str, Any]], via: str) -> Optional[Dict[str, Any]]:
    """The locator of the link / button named `via` on its source page: its id or test id when it has one (a name
    alone collides — the "Log in" nav link and the "Log in" form button), else role + name."""
    for el in elements or []:
        role = (el.get("semantic_locators") or {}).get("role") or el.get("aria_role")
        name = (el.get("display_text") or ((el.get("playwright_locators") or {}).get("get_by_role") or {}).get("name") or "")
        if role not in ("link", "button") or name.strip() != via:
            continue
        # discovery's own candidates, in its order, that are UNIQUE on the page (a shared test id is not — counted
        # here as well, for app maps recorded before discovery checked it)
        def shared(kind: str, value: Any) -> bool:
            return sum(1 for e in elements if (e.get("attribute_locators") or {}).get(kind) == value) > 1
        for cand in el.get("locator_candidates") or []:
            v = cand.get("value") or {}
            if cand.get("unique") is not True or (cand.get("type") in ("id", "testid")
                                                  and shared(cand["type"], v.get(cand["type"]))):
                continue
            if cand.get("type") == "id" and _CSS_SAFE.match(str(v.get("id") or "")):
                return {"type": "css", "locator": f"#{v['id']}"}
            if cand.get("type") == "testid" and v.get("testid"):
                return {"type": "css", "locator": f'[data-testid="{_css_attr(str(v["testid"]))}"]'}
            if cand.get("type") == "role" and v.get("role") and v.get("name"):
                return {"type": "role", "locator": v["role"], "name": v["name"]}
        return {"type": "role", "locator": role, "name": via}
    return None


def merge_transition_locators(locator_map: Dict[str, Dict[str, Any]], inp: DesignInputs,
                              cases: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """State-transition cases name their trigger element by its accessible name only; give each one a locator key
    (case["locator_keys"]["trigger"], and "trigger_2" for the second step of a 1-switch case) pointing at that
    element ON ITS SOURCE PAGE, so the plan cannot pick a same-named element of another page."""
    result = dict(locator_map)
    by_value = {_value_key(e): k for k, e in result.items()}
    added: List[str] = []
    for case in sorted(cases, key=lambda c: c["id"]):
        if case.get("technique") != "state_transition" or (case.get("target") or {}).get("kind") != "transition":
            continue
        parts = (case.get("key") or "").split("|")
        if parts[:2] == ["st", "0"] and len(parts) >= 5:
            hops = [(parts[2], "|".join(parts[4:]))]
        elif parts[:2] == ["st", "1"] and len(parts) >= 7:
            hops = [(parts[2], parts[5]), (parts[3], "|".join(parts[6:]))]
        else:
            continue
        keys: Dict[str, str] = {}
        for i, (page, via) in enumerate(hops):
            st = inp.states.get(page)
            entry = _trigger_entry(st.elements if st else [], via) if via else None
            if entry is None:
                continue
            entry.update({"description": f"{via} ({entry.get('locator') if entry['type'] == 'role' else 'element'} on {page})",
                          "_module_id": case.get("module_id"), "_source": "app_map",
                          "_page_url": st.sample_url if st else None})
            existing = by_value.get(_value_key(entry))
            if existing:
                key = existing
            else:
                base = _slug(f"{via} on {page.strip('/') or 'home'}")
                key, n = base, 2
                while key in result:
                    key = f"{base}_{n}"
                    n += 1
                result[key] = entry
                by_value[_value_key(entry)] = key
                added.append(key)
            keys["trigger" if i == 0 else f"trigger_{i + 1}"] = key
        if keys:
            case["locator_keys"] = {**(case.get("locator_keys") or {}), **keys}
    return result, added


def update_locator_map_file(path: str, inp: DesignInputs, cases: List[Dict[str, Any]]) -> List[str]:
    current: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            current = json.load(fh) or {}
    merged, added = merge_form_locators(current, inp, cases)
    merged, added_t = merge_transition_locators(merged, inp, cases)
    added = added + added_t
    if added:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        os.replace(tmp, path)
    return added
