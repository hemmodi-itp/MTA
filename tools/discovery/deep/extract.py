"""
extract.py — Phase 2 deep element extraction (tasks 2.1 + 2.2).

    result = extract_page(page, cfg, url_allowed=policy.url_allowed)
    result["elements"]   # dom_elements.json element dicts (legacy shape + deep fields)
    result["scan"]       # stats: duration, frames, shadow roots, scoped locators, limitations

One `frame.evaluate(extract.js)` per frame replaces the legacy scanner's ~19 Playwright
round trips per element. The legacy fields of every classic element are built by the
same Python function the legacy scanner uses (tools.playwright_scanner.build_element_data),
so ids and merge comparisons stay stable (design §2 R1/R4).

Deep-only fields (never part of the locator identity, except a non-empty frame path):
    capture_mode "deep", capture_reason, tag_name, aria_role, constraints, containers,
    state_hints, frame {path, url} (child frames only), shadow (open shadow DOM only), href (links).

Scoped role locators (design §4.3): for a (role, name) pair that occurs more than once in a
frame, each named container candidate is tried in the browser —
frame.get_by_role(container).get_by_role(role, name=name) — and kept only when it matches
exactly one element and that element is the one being described.
"""

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.discovery.deep.config import DiscoveryConfig, load_config
from tools.playwright_scanner import (
    ELEMENT_ATTRIBUTES,
    _demote_duplicate_role_candidates,
    build_element_data,
)

_log = logging.getLogger("workflow.discovery.deep")

_JS_PATH = os.path.join(os.path.dirname(__file__), "extract.js")
with open(_JS_PATH, encoding="utf-8") as _f:
    EXTRACT_JS = _f.read()

# Legacy selector order and `tag` values (PlaywrightScanner.scan_page) — must not change (R1).
CLASSIC_SELECTORS: List[Tuple[str, str]] = [
    ("input", "input"),
    ("button", "button"),
    ("select", "select"),
    ("textarea", "textarea"),
    ("a", "a"),
    ("[role=combobox]", "combobox"),
]

_EXTRA_ROLES = ("button", "link", "tab", "menuitem", "menuitemcheckbox", "menuitemradio", "checkbox", "radio",
                "switch", "slider", "spinbutton", "option", "treeitem", "searchbox", "textbox")
EXTRA_SELECTORS: List[Tuple[str, str]] = (
    [(f"[role={r}]", f"role:{r}") for r in _EXTRA_ROLES]
    + [
        ('[contenteditable]:not([contenteditable="false"])', "contenteditable"),
        ("[onclick]", "onclick"),
        ('[tabindex]:not([tabindex="-1"])', "tabindex"),
        ("summary", "summary"),
        ("details", "details"),
    ]
)

_TYPED_INPUTS = {"file", "date", "datetime-local", "time", "range", "color"}

SCOPED_SCORE = 105   # above a demoted role (60), below a unique testid (150)

FRAME_SELECTOR_JS = r"""el => {
  const q = s => s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const root = el.getRootNode();
  const cands = [];
  if (el.id) cands.push('#' + CSS.escape(el.id));
  for (const a of ['name', 'title', 'src']) {
    const v = el.getAttribute(a);
    if (v) cands.push(`${el.tagName.toLowerCase()}[${a}="${q(v)}"]`);
  }
  for (const c of cands) { try { if (root.querySelectorAll(c).length === 1) return c; } catch (e) { /* next */ } }
  const parts = [];
  let e = el;
  while (e && e.nodeType === 1 && e !== document.documentElement) {
    let i = 1, s = e.previousElementSibling;
    while (s) { if (s.nodeName === e.nodeName) i++; s = s.previousElementSibling; }
    parts.unshift(e.nodeName.toLowerCase() + ':nth-of-type(' + i + ')');
    e = e.parentElement;
  }
  return (root === document ? 'html > ' : '') + parts.join(' > ');
}"""

LIMITATIONS = ["closed shadow roots are not reachable from page scripts"]


def _frame_path(frame) -> List[str]:
    """Selectors from the top page down to *frame*, one per <iframe>/<frame> element."""
    chain: List[str] = []
    f = frame
    while f.parent_frame is not None:
        handle = f.frame_element()
        chain.insert(0, f.parent_frame.evaluate(FRAME_SELECTOR_JS, handle))
        f = f.parent_frame
    return chain


def _frame_allowed(frame, url_allowed: Optional[Callable[[str], bool]]) -> Tuple[bool, str]:
    url = frame.url or ""
    if url.startswith(("about:", "data:")) or not url:
        return True, ""
    if url_allowed is not None and not url_allowed(url):
        return False, "host_not_allowed"
    return True, ""


def _build_element(rec: Dict[str, Any], locator_number: int, frame_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    css, xpath = rec.get("css") or "", rec.get("xpath")
    data = build_element_data(
        rec.get("values") or {}, (rec.get("text") or "").strip(), rec.get("label") or "",
        bool(rec.get("visible")), bool(rec.get("enabled")), rec.get("tag_name") or "",
        css_fn=lambda: css, xpath_fn=lambda: xpath,
    )
    tag = rec.get("tag") or rec.get("tag_name") or "el"
    reason = rec.get("reason") or "classic"
    if reason == "classic" and rec.get("tag_name") == "input":
        itype = ((rec.get("values") or {}).get("type") or "").lower()
        if itype in _TYPED_INPUTS:
            reason = f"input:{itype}"
    element: Dict[str, Any] = {"locator_id": f"LOC-{locator_number:04d}", "tag": tag, **data}
    element["capture_mode"] = "deep"
    element["capture_reason"] = reason
    element["tag_name"] = rec.get("tag_name")
    element["aria_role"] = rec.get("aria_role")
    if rec.get("constraints"):
        element["constraints"] = rec["constraints"]
    if rec.get("containers"):
        element["containers"] = rec["containers"]
    hints = {k: v for k, v in (rec.get("state") or {}).items() if v not in (None, "", False)}
    if hints:
        element["state_hints"] = hints
    if frame_info:
        element["frame"] = frame_info
    if rec.get("in_shadow"):
        element["shadow"] = True
    if rec.get("href"):
        element["href"] = rec["href"]
    return element


def _role_pair(el: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    r = (el.get("playwright_locators") or {}).get("get_by_role") or {}
    if r.get("role") and r.get("name"):
        return r["role"], r["name"]
    return None


def _verify_scoped(frame, el: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    pair = _role_pair(el)
    if not pair:
        return None
    role, name = pair
    for cand in el.get("containers") or []:
        try:
            scope = (frame.get_by_role(cand["role"], name=cand["name"]) if cand.get("name")
                     else frame.get_by_role(cand["role"]))
            loc = scope.get_by_role(role, name=name)
            if loc.count() != 1:
                continue
            if loc.evaluate("el => el.__mtaIdx") != index:
                continue
            return {"type": "scoped_role",
                    "value": {"container": {"role": cand["role"], "name": cand.get("name")}, "role": role, "name": name},
                    "score": SCOPED_SCORE, "unique": True, "match_count": 1}
        except Exception:
            continue
    return None


def extract_page(page, cfg: Optional[DiscoveryConfig] = None,
                 url_allowed: Optional[Callable[[str], bool]] = None,
                 verify_scopes: bool = True) -> Dict[str, Any]:
    cfg = load_config(cfg.model_dump() if isinstance(cfg, DiscoveryConfig) else cfg)
    started = time.monotonic()
    elements: List[Dict[str, Any]] = []
    frames_scanned: List[str] = []
    frames_skipped: List[Dict[str, str]] = []
    shadow_roots = 0
    pointer_capped = False
    duplicates = verified = 0
    counter = 1

    frames = [page.main_frame] + ([f for f in page.frames if f is not page.main_frame] if cfg.capture.frames else [])
    for frame in frames:
        is_main = frame is page.main_frame
        if not is_main:
            if frame.is_detached():
                continue
            ok, why = _frame_allowed(frame, url_allowed)
            if not ok:
                frames_skipped.append({"url": frame.url, "reason": why})
                continue
        try:
            frame_info = None if is_main else {"path": _frame_path(frame), "url": frame.url}
            js_cfg = {
                "attributes": ELEMENT_ATTRIBUTES,
                "classic": [list(x) for x in CLASSIC_SELECTORS],
                "extra": [list(x) for x in EXTRA_SELECTORS],
                "shadow": cfg.capture.shadow,
                "cursor_pointer": cfg.capture.cursor_pointer,
                "max_pointer": cfg.capture.max_pointer,
                "start_index": 0,
            }
            out = frame.evaluate(EXTRACT_JS, js_cfg)
        except Exception as exc:
            frames_skipped.append({"url": frame.url, "reason": f"extract_failed: {type(exc).__name__}"})
            if is_main:
                raise
            continue
        frames_scanned.append(frame.url)
        stats = out.get("stats") or {}
        shadow_roots += int(stats.get("shadow_roots") or 0)
        pointer_capped = pointer_capped or bool(stats.get("pointer_capped"))

        frame_elements: List[Tuple[Dict[str, Any], int]] = []
        for rec in out.get("records") or []:
            frame_elements.append((_build_element(rec, counter, frame_info), rec["index"]))
            counter += 1
        els = [e for e, _ in frame_elements]
        _demote_duplicate_role_candidates(els)      # unchanged legacy demotion, per frame

        if verify_scopes:
            counts: Dict[Tuple[str, str], int] = {}
            for e in els:
                pair = _role_pair(e)
                if pair:
                    counts[pair] = counts.get(pair, 0) + 1
            for e, idx in frame_elements:
                pair = _role_pair(e)
                if not pair or counts.get(pair, 0) <= 1:
                    continue
                duplicates += 1
                cand = _verify_scoped(frame, e, idx)
                if cand:
                    verified += 1
                    cands = [c for c in (e.get("locator_candidates") or []) if c.get("type") != "scoped_role"]
                    cands.append(cand)
                    cands.sort(key=lambda c: c["score"], reverse=True)
                    e["locator_candidates"] = cands
                    e["recommended_locator"] = cands[0]
        elements.extend(els)

    scan = {
        "mode": "deep",
        "duration_s": round(time.monotonic() - started, 3),
        "frames_scanned": len(frames_scanned),
        "frames_skipped": frames_skipped,
        "shadow_roots": shadow_roots,
        "pointer_capped": pointer_capped,
        "duplicate_role_names": duplicates,
        "scoped_verified": verified,
        "element_count": len(elements),
        "limitations": list(LIMITATIONS),
    }
    return {"elements": elements, "scan": scan}
