"""
identity.py — Phase 6.3: locator identity check. A healed locator must point at the SAME element the original
locator meant, not merely at "an element that exists".

Fingerprint (what a person would recognise an element by — never the attributes a refactor renames):
    tag, role (explicit or implicit), name (accessible name), label (associated <label>), container (closest
    form / nav / main / dialog / list ... by its accessible name, not its id), position (index among same-role
    elements in that container, and how many there are). Ids, test ids, classes and name attributes are kept
    only as a tie-break hint (`attrs`), because those are exactly what a locator change renames.

Score 0..1 (weights below). A heal is accepted when the best candidate scores >= THRESHOLD and beats the
runner-up by >= MARGIN; otherwise it goes to human review — two equally good candidates are a guess, not a heal.
A candidate whose accessible name is clearly different (similarity < NAME_FLOOR, both named) is never eligible:
when an element is removed, its neighbour often takes its slot in the same container.

Sources of the ORIGINAL fingerprint, best first:
    1. `_fingerprint` stored on the locator_map.json entry while it still resolved (ScriptGeneration's live
       validation, or `python -m tools.healing.identity capture --project X`);
    2. the DOM-scan element the entry was built from (dom_elements.json, static: no position);
    3. the entry itself (role/name/description) — weakest.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

THRESHOLD = 0.75
MARGIN = 0.08
NAME_FLOOR = 0.5        # both have an accessible name: below this similarity it is a different element, full stop
WEIGHTS = {"role": 0.20, "name": 0.30, "tag": 0.10, "label": 0.10, "container": 0.15, "position": 0.15}
_NEUTRAL = 0.5          # a signal neither side has says nothing either way

# fingerprint of one element, evaluated in the page — shared with the TS runtime's failure-time probe
FINGERPRINT_SOURCE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "application_assets", "_shared",
                                       "runtime", "fixtures", "fingerprint.js")
with open(FINGERPRINT_SOURCE_PATH, encoding="utf-8") as _fh:
    _FP_FN = _fh.read()

FINGERPRINT_JS = "(el) => {" + _FP_FN + " return mtaFingerprint(el); }"

# Runs in the page: fingerprints of every visible element with the original's tag or role, each with a locator
# suggestion (unique test id > unique #id > unique tag[name] > role+name > nth-of-type CSS path).
CANDIDATES_JS = "([want, testIdAttr]) => {" + _FP_FN + r"""
  const unique = (sel) => { try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; } };
  const cssPath = (el) => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.body; n = n.parentElement) {
      const same = [...n.parentElement.children].filter((c) => c.tagName === n.tagName);
      parts.unshift(n.tagName.toLowerCase() + (same.length > 1 ? `:nth-of-type(${same.indexOf(n) + 1})` : ''));
    }
    return 'body > ' + parts.join(' > ');
  };
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (out.length >= 300) break;
    const fp = mtaFingerprint(el);
    if (!(fp.tag === want.tag || (want.role && fp.role === want.role))) continue;
    if (!visible(el)) continue;
    let entry = null;
    const tid = el.getAttribute(testIdAttr);
    if (tid && unique(`[${testIdAttr}="${CSS.escape(tid)}"]`)) entry = {type: 'testid', locator: tid};
    else if (el.id && unique(`#${CSS.escape(el.id)}`)) entry = {type: 'css', locator: `#${CSS.escape(el.id)}`};
    else if (fp.attrs.name && unique(`${fp.tag}[name="${CSS.escape(fp.attrs.name)}"]`))
      entry = {type: 'css', locator: `${fp.tag}[name="${CSS.escape(fp.attrs.name)}"]`};
    else if (fp.role && fp.name) entry = {type: 'role', locator: fp.role, name: fp.name};
    else entry = {type: 'css', locator: cssPath(el)};
    out.push({fingerprint: fp, entry});
  }
  return out;
}"""


# ── scoring ──────────────────────────────────────────────────────────────────

def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def text_similarity(a: Any, b: Any) -> Optional[float]:
    """0..1, or None when both are empty (no signal). Token-set ratio, so word order does not matter."""
    a, b = _norm(a), _norm(b)
    if not a and not b:
        return None
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    wa, wb = set(re.findall(r"\w+", a)), set(re.findall(r"\w+", b))
    ta, tb = " ".join(sorted(wa)), " ".join(sorted(wb))
    sim = max(difflib.SequenceMatcher(None, a, b).ratio(), difflib.SequenceMatcher(None, ta, tb).ratio())
    # no word in common: letters alone overrate short names ("name" is inside "nickname") — discount them
    return sim if wa & wb else round(sim * 0.6, 3)


def _container_similarity(a: Any, b: Any) -> Optional[float]:
    """Containers are landmark paths + the innermost one's name ("main>form|Add product"). Same path: 0.5..1 by the
    name; one path nested in the other (moved into a nav inside the same footer): 0.6; same outermost landmark: 0.4."""
    if not a and not b:
        return None
    if not a or not b:
        return 0.3
    if a == b:
        return 1.0
    pa, _, na = str(a).partition("|")
    pb, _, nb = str(b).partition("|")
    if pa == pb:
        sim = text_similarity(na, nb)
        return 0.6 if sim is None else 0.5 + 0.5 * sim
    ta, tb = pa.split(">"), pb.split(">")
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if long_[:len(short)] == short:
        return 0.6
    return 0.4 if ta[0] == tb[0] else 0.0


def _position_similarity(a: Any, b: Any) -> Optional[float]:
    if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)) or len(a) < 2 or len(b) < 2:
        return None
    if a[0] is None or b[0] is None or a[0] < 0 or b[0] < 0:
        return None
    if a[0] == b[0]:
        return 1.0
    return 0.5 if abs(a[0] - b[0]) == 1 else 0.0


def identity_score(original: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """{"score": 0..1, "parts": {signal: 0..1 | None}}; a signal neither side has counts as neutral."""
    parts = {
        "role": (None if not original.get("role") and not candidate.get("role")
                 else float(_norm(original.get("role")) == _norm(candidate.get("role")))),
        "name": text_similarity(original.get("name"), candidate.get("name")),
        "tag": (None if not original.get("tag") or not candidate.get("tag")
                else float(_norm(original.get("tag")) == _norm(candidate.get("tag")))),
        "label": text_similarity(original.get("label"), candidate.get("label")),
        "container": _container_similarity(original.get("container"), candidate.get("container")),
        # a position is only comparable among peers of the same container
        "position": (_position_similarity(original.get("position"), candidate.get("position"))
                     if original.get("container") == candidate.get("container") else None),
    }
    score = sum(WEIGHTS[k] * (_NEUTRAL if v is None else v) for k, v in parts.items())
    # Position and container can line up by accident (the element was removed and its neighbour took its slot):
    # a clearly different name always disqualifies, whatever the total.
    eligible = parts["name"] is None or parts["name"] >= NAME_FLOOR
    return {"score": round(score, 3), "eligible": eligible,
            "parts": {k: (None if v is None else round(v, 3)) for k, v in parts.items()}}


def _attr_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> int:
    aa, bb = a.get("attrs") or {}, b.get("attrs") or {}
    return sum(1 for k in ("id", "testid", "name") if aa.get(k) and aa.get(k) == bb.get(k))


def choose(original: Dict[str, Any], candidates: List[Dict[str, Any]],
           threshold: float = THRESHOLD, margin: float = MARGIN) -> Dict[str, Any]:
    """Pick the candidate that is the same element. candidates: [{"fingerprint", "entry"}].

    Returns {"accepted": bool, "best": candidate+score | None, "runner_up_score", "reason"}."""
    scored = []
    for c in candidates:
        s = identity_score(original, c.get("fingerprint") or {})
        if s["eligible"]:
            scored.append({**c, "score": s["score"], "parts": s["parts"]})
    scored.sort(key=lambda c: (-c["score"], -_attr_overlap(original, c.get("fingerprint") or {})))
    if not scored:
        return {"accepted": False, "best": None, "runner_up_score": None,
                "reason": "no candidate element on the page with a similar name"}
    best = scored[0]
    runner = scored[1]["score"] if len(scored) > 1 else 0.0
    if best["score"] < threshold:
        return {"accepted": False, "best": best, "runner_up_score": runner,
                "reason": f"best candidate scores {best['score']} < {threshold} — not the same element; human review"}
    if best["score"] - runner < margin and _attr_overlap(original, best["fingerprint"]) <= \
            _attr_overlap(original, scored[1]["fingerprint"]):
        return {"accepted": False, "best": best, "runner_up_score": runner,
                "reason": f"ambiguous: two candidates score {best['score']} and {runner} — human review"}
    return {"accepted": True, "best": best, "runner_up_score": runner, "reason": "identity match"}


# ── original fingerprints from what was recorded ──────────────────────────────

def fingerprint_from_dom_element(el: Dict[str, Any]) -> Dict[str, Any]:
    """Static fingerprint from a dom_elements.json element (no position: the scan does not record it)."""
    sem = el.get("semantic_locators") or {}
    pw = el.get("playwright_locators") or {}
    role = el.get("aria_role") or sem.get("role") or ((pw.get("get_by_role") or {}).get("role")) or ""
    name = (sem.get("aria_label") or ((pw.get("get_by_role") or {}).get("name")) or el.get("display_text")
            or sem.get("label") or sem.get("placeholder") or sem.get("title") or "")
    containers = el.get("containers") or []
    c = containers[0] if containers and isinstance(containers[0], dict) else {}
    tag_of_role = {"main": "main", "navigation": "nav", "form": "form", "dialog": "dialog", "list": "ul"}
    container = f"{tag_of_role.get(c.get('role'), c.get('role') or '')}|{(c.get('name') or '')[:60]}" if c else ""
    attrs = el.get("attribute_locators") or {}
    return {"tag": el.get("tag_name") or el.get("tag") or "", "role": role, "name": str(name)[:120],
            "label": str(sem.get("label") or "")[:120], "container": container, "position": None,
            "attrs": {"id": attrs.get("id") or "", "testid": attrs.get("testid") or "", "name": attrs.get("name") or "",
                      "type": attrs.get("type") or ""}}


_DESC_SUFFIX = re.compile(r"\s*\((?:[^()]*on /[^()]*)\)\s*$")
_ROLE_WORDS = {"button": "button", "link": "link", "checkbox": "checkbox", "field": "textbox", "input": "textbox",
               "dropdown": "combobox", "select": "combobox", "heading": "heading"}


def fingerprint_from_entry(entry: Dict[str, Any], key: str = "") -> Dict[str, Any]:
    """Weakest source: what the locator_map entry itself says (role/name for role entries, else its description)."""
    if entry.get("type") == "role":
        role, name = entry.get("locator", ""), entry.get("name", "")
    else:
        desc = _DESC_SUFFIX.sub("", str(entry.get("description") or ""))
        words = desc.lower().split()
        role = next((_ROLE_WORDS[w] for w in reversed(words) if w in _ROLE_WORDS), "")
        name = " ".join(w for w in desc.split() if w.lower() not in _ROLE_WORDS) or key.replace("_", " ")
        if entry.get("type") in ("label", "placeholder", "text"):
            name = entry.get("locator", "") or name
    return {"tag": "", "role": role, "name": name[:120], "label": "", "container": "", "position": None, "attrs": {}}


def original_fingerprint(entry: Dict[str, Any], key: str = "",
                         dom_element: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], str]:
    """(fingerprint, source) — see the module docstring for the order."""
    if isinstance(entry.get("_fingerprint"), dict):
        return entry["_fingerprint"], "recorded"
    if dom_element:
        return fingerprint_from_dom_element(dom_element), "dom_scan"
    return fingerprint_from_entry(entry, key), "entry"


# ── live helpers (sync Playwright page) ──────────────────────────────────────

def live_fingerprint(page, entry: Dict[str, Any], test_id_attribute: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fingerprint of the one element the entry resolves to, or None (0 or 2+ matches, or an error)."""
    from tools.test_creation.script_generator.locator_resolve import resolve_entry
    try:
        loc = resolve_entry(page, entry, test_id_attribute)
        if loc.count() != 1:
            return None
        return loc.evaluate(FINGERPRINT_JS)
    except Exception:
        return None


def live_candidates(page, original: Dict[str, Any], test_id_attribute: Optional[str] = None) -> List[Dict[str, Any]]:
    want = {"tag": original.get("tag") or "", "role": original.get("role") or ""}
    try:
        return page.evaluate(CANDIDATES_JS, [want, test_id_attribute or "data-testid"]) or []
    except Exception:
        return []


def heal_live(page, original: Dict[str, Any], test_id_attribute: Optional[str] = None,
              threshold: float = THRESHOLD) -> Dict[str, Any]:
    """Find the original element on the live page by identity; the chosen entry must resolve to exactly that
    element. Returns choose()'s result plus "entry" when accepted."""
    from tools.test_creation.script_generator.locator_resolve import entry_resolves
    result = choose(original, live_candidates(page, original, test_id_attribute), threshold=threshold)
    if not result["accepted"]:
        return result
    entry = dict(result["best"]["entry"])
    if not entry_resolves(page, entry, test_id_attribute):
        return {**result, "accepted": False, "reason": f"suggested locator {entry} does not resolve to one element"}
    return {**result, "entry": entry}


# ── capture CLI ──────────────────────────────────────────────────────────────

def capture_fingerprints(page, locator_map: Dict[str, Any], keys: List[str],
                         test_id_attribute: Optional[str] = None, overwrite: bool = False) -> List[str]:
    """Record `_fingerprint` on each entry that resolves to exactly one element; returns the keys updated."""
    done = []
    for key in keys:
        entry = locator_map.get(key)
        if not isinstance(entry, dict) or (entry.get("_fingerprint") and not overwrite):
            continue
        fp = live_fingerprint(page, entry, test_id_attribute)
        if fp:
            entry["_fingerprint"] = fp
            done.append(key)
    return done


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Record locator identity fingerprints (Phase 6.3) while locators work.")
    ap.add_argument("command", choices=["capture"])
    ap.add_argument("--project", required=True)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)

    from tools.constants import PROJECTS_BASE
    from tools.execution.config import load_execution_config
    from tools.playwright_scanner import PlaywrightScanner
    import yaml

    pdir = os.path.join(PROJECTS_BASE, args.project)
    map_path = os.path.join(pdir, "test_creation", "locator_map.json")
    with open(map_path, encoding="utf-8") as fh:
        locator_map = json.load(fh)
    with open(os.path.join(pdir, "project.yaml"), encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    modules = {m["id"]: m for m in cfg.get("modules") or [] if isinstance(m, dict) and m.get("id")}
    default_url = (cfg.get("project") or {}).get("url") or cfg.get("url") or ""
    tid = load_execution_config(args.project)["test_id_attribute"]
    groups: Dict[Tuple[str, str], List[str]] = {}
    for key, entry in locator_map.items():
        if isinstance(entry, dict) and not entry.get("_dynamic"):
            mid = entry.get("_module_id") or "_default"
            url = entry.get("_page_url") or (modules.get(mid) or {}).get("url") or default_url
            groups.setdefault((mid, url), []).append(key)
    updated: List[str] = []
    for (mid, url), keys in groups.items():
        if not url:
            continue
        scanner = PlaywrightScanner(headless=True)       # same page setup as ScriptGeneration's live validation
        try:
            page = scanner.launch()
            if (modules.get(mid) or {}).get("setup"):
                scanner._execute_setup_steps(page, modules[mid]["setup"])
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            updated += capture_fingerprints(page, locator_map, keys, tid, args.overwrite)
        except Exception as exc:
            print(f"skip {mid} {url}: {exc}")
        finally:
            try:
                scanner.close()
            except Exception:
                pass
    with open(map_path, "w", encoding="utf-8") as fh:
        json.dump(locator_map, fh, indent=2)
    print(f"recorded {len(updated)} fingerprint(s) in {map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
