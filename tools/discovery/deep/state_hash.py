"""
state_hash.py — deduplicate UI states by URL template + DOM *structure* (design §2 R14).

Two visits are the same state when they share a URL template and the same structural hash:
the sorted multiset of interactive-element signatures plus a landmark/heading skeleton.
Text, values, element order and digit runs inside ids are ignored, so a product page for
item 3 and item 42 — or a list with different data — collapse into one state, while an
opened dialog / expanded accordion / added form field produces a new one.
"""

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional

_DIGITS = re.compile(r"\d+")

# Landmark / heading skeleton (tag counts), one evaluate per state.
SKELETON_JS = r"""() => {
  const sel = ['main', 'nav', 'header', 'footer', 'aside', 'form', 'dialog[open]', '[role=dialog]', 'table',
               'h1', 'h2', 'h3', '[role=tabpanel]', 'details[open]'];
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const out = {};
  for (const s of sel) out[s] = [...document.querySelectorAll(s)].filter(vis).length;
  return out;
}"""


def _norm_id(value: Optional[str]) -> str:
    return _DIGITS.sub("#", value or "")


def element_signature(el: Dict[str, Any]) -> str:
    attrs = el.get("attribute_locators") or {}
    frame = " >> ".join(((el.get("frame") or {}).get("path")) or [])
    visible = bool((el.get("quality") or {}).get("visible"))
    return "|".join([
        el.get("tag_name") or el.get("tag") or "",
        el.get("aria_role") or (el.get("semantic_locators") or {}).get("role") or "",
        (attrs.get("type") or "").lower(),
        _norm_id(attrs.get("name")),
        _norm_id(attrs.get("id")),
        "v" if visible else "h",
        frame,
    ])


def structural_hash(elements: Iterable[Dict[str, Any]], skeleton: Optional[Dict[str, int]] = None) -> str:
    sigs: List[str] = sorted(element_signature(e) for e in elements)
    skel = sorted(f"{k}={int(v)}" for k, v in (skeleton or {}).items())
    h = hashlib.sha256()
    h.update("\n".join(sigs).encode("utf-8"))
    h.update(b"\n--\n")
    h.update("\n".join(skel).encode("utf-8"))
    return h.hexdigest()[:16]


def state_id(url_template: str, struct_hash: str) -> str:
    return "S-" + hashlib.sha1(f"{url_template}|{struct_hash}".encode("utf-8")).hexdigest()[:10]
