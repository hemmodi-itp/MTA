"""
forms.py — observed validation oracle (task 2.3) -> form_model.json records.

For every form the crawl finds (a <form>, or a "virtual form": loose fields grouped under the
nearest container that holds a button), MTA submits it empty, then with each field invalid in
turn while the other fields hold deterministic valid values, and records what the app really
says: native validationMessage, visible error text (attributed to a field where possible),
aria-invalid, focus, the network calls made, and whether the app *accepted* the bad input.

Safety (design §2 R7, decision D3):
  * environment local/dev/staging -> full probes (write requests allowed during the submit only);
  * prod / unspecified            -> client-only: every non-GET request is aborted by WriteGuard,
                                     so nothing reaches the server;
  * a destructive submit (tools/safety/action_classifier) is never probed unless the policy
    allows destructive actions; forms without fillable fields (checkout, delete, logout) and
    GET forms without declared constraints (search) are listed, not probed.

plan_probes() is pure and deterministic: same form -> same probes, same values.
"""

import base64
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.discovery.deep.config import DiscoveryConfig

_log = logging.getLogger("workflow.discovery.deep")

_JS_PATH = os.path.join(os.path.dirname(__file__), "forms.js")
with open(_JS_PATH, encoding="utf-8") as _f:
    FORMS_JS = _f.read()

TEXT_TYPES = {"text", "search", "tel", "password", "email", "url", "textarea", "contenteditable", ""}
FIXED_DATE = "2026-01-15"
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

PATTERN_VALID_CANDIDATES = ["Test", "test", "TEST", "12345", "Test123", "test@example.com", "ABC-123", "a", "1"]
PATTERN_INVALID_CANDIDATES = ["!!!", " ", "a", "1", "~", "Test value 1"]


# ── form identity / eligibility ───────────────────────────────────────────

def form_fingerprint(url_template: str, form: Dict[str, Any]) -> str:
    names = sorted((f.get("name") or f.get("id") or f.get("label") or f.get("type") or "") for f in form.get("fields") or [])
    ident = form.get("id") or form.get("name") or form.get("action") or form.get("aria_label") or form.get("kind")
    raw = json.dumps([url_template, ident, (form.get("submit") or {}).get("text"), names], sort_keys=True)
    return "F-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def field_name(f: Dict[str, Any]) -> str:
    return f.get("name") or f.get("id") or re.sub(r"[^a-z0-9]+", "_", (f.get("label") or "").lower()).strip("_") or f["key"]


def fillable(f: Dict[str, Any]) -> bool:
    return bool(f.get("visible")) and not f.get("disabled") and not f.get("readonly")


def _has_constraints(f: Dict[str, Any]) -> bool:
    return any(f.get(k) not in (None, False, "") for k in ("required", "aria_required", "maxlength", "minlength",
                                                           "min", "max", "pattern", "accept"))


def skip_reason(form: Dict[str, Any], destructive_submit: bool, destructive_allowed: bool) -> Optional[str]:
    fields = [f for f in form.get("fields") or [] if fillable(f)]
    if not fields:
        return "no_fillable_fields"
    if not form.get("submit") and form.get("kind") == "virtual":
        return "no_submit_control"
    if destructive_submit and not destructive_allowed:
        return "destructive_submit"
    if (form.get("method") or "get") == "get" and form.get("kind") == "form" and not any(_has_constraints(f) for f in fields):
        return "get_form_no_constraints"
    return None


# ── deterministic values ──────────────────────────────────────────────────

def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else repr(n)


def _accept_exts(accept: Optional[str]) -> List[str]:
    return [a.strip().lower() for a in (accept or "").split(",") if a.strip().startswith(".")]


def _file_payload(ext: str) -> Dict[str, Any]:
    ext = ext if ext.startswith(".") else "." + ext
    if ext == ".png":
        return {"name": "mta_probe.png", "mimeType": "image/png", "buffer": _PNG_1X1}
    if ext == ".csv":
        return {"name": "mta_probe.csv", "mimeType": "text/csv", "buffer": b"a,b\n1,2\n"}
    if ext in (".jpg", ".jpeg"):
        return {"name": "mta_probe" + ext, "mimeType": "image/jpeg", "buffer": b"\xff\xd8\xff\xd9"}
    if ext == ".pdf":
        return {"name": "mta_probe.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\n%%EOF\n"}
    return {"name": "mta_probe" + ext, "mimeType": "text/plain", "buffer": b"mta probe\n"}


def _pattern_ok(pattern: str, value: str) -> Optional[bool]:
    try:
        return re.fullmatch(pattern, value) is not None
    except re.error:
        return None


def valid_action(f: Dict[str, Any]) -> Tuple[Optional[Tuple[str, Any]], str]:
    """(action, rule) giving *f* a valid value; action None = leave untouched."""
    t = f.get("type") or "text"
    name = (f.get("name") or f.get("id") or f.get("label") or "").lower()
    if t == "select":
        opts = [o for o in f.get("options") or [] if o.get("value") not in ("", None) and not o.get("disabled")]
        return (("select", opts[0]["value"]), "first non-empty option") if opts else (None, "no selectable option")
    if t == "checkbox":
        return (("check", True), "checked") if (f.get("required") or f.get("aria_required")) else (None, "left as is")
    if t == "radio":
        return ("check", True), "checked"
    if t == "file":
        exts = _accept_exts(f.get("accept"))
        return ("file", _file_payload(exts[0] if exts else ".txt")), f"file {exts[0] if exts else '.txt'}"
    if t in ("number", "range"):
        lo, hi = _num(f.get("min")), _num(f.get("max"))
        v = lo if lo is not None else 1.0
        if hi is not None and v > hi:
            v = hi
        return ("fill", _fmt(v)), "min" if lo is not None else "1"
    if t == "date":
        v = FIXED_DATE
        if f.get("min") and v < f["min"]:
            v = f["min"]
        if f.get("max") and v > f["max"]:
            v = f["max"]
        return ("fill", v), "fixed date"
    if t == "time":
        return ("fill", "12:00"), "noon"
    if t == "datetime-local":
        return ("fill", FIXED_DATE + "T12:00"), "fixed datetime"
    if t == "month":
        return ("fill", FIXED_DATE[:7]), "fixed month"
    if t == "week":
        return ("fill", "2026-W03"), "fixed week"
    if t == "color":
        return ("fill", "#336699"), "fixed color"
    if t == "email":
        return ("fill", "qa@example.com"), "email"
    if t == "url":
        return ("fill", "https://example.com"), "url"
    if t == "tel":
        return ("fill", "5551234567"), "tel"
    if t == "password":
        return ("fill", "Probe-Passw0rd!"), "password"
    if (f.get("inputmode") in ("decimal", "numeric")) or re.search(r"price|amount|qty|quantity|total|cost", name):
        return ("fill", "10"), "numeric text"
    value = "Test"
    if f.get("minlength") and f["minlength"] > len(value):
        value = "T" * int(f["minlength"])
    if f.get("maxlength") is not None and f["maxlength"] < len(value):
        value = value[: max(1, int(f["maxlength"]))]
    if f.get("pattern"):
        for cand in PATTERN_VALID_CANDIDATES:
            if _pattern_ok(f["pattern"], cand):
                return ("fill", cand), "matches pattern"
        return ("fill", value), "pattern unmatched (valid value uncertain)"
    return ("fill", value), "text"


def invalid_probes(f: Dict[str, Any], cfg: DiscoveryConfig) -> List[Tuple[str, Tuple[str, Any], str]]:
    """[(probe kind, action, value rule)] for one field, in a fixed order."""
    t = f.get("type") or "text"
    out: List[Tuple[str, Tuple[str, Any], str]] = []
    required = f.get("required") or f.get("aria_required")
    if required:
        if t == "checkbox":
            out.append(("required_missing", ("check", False), "unchecked"))
        elif t == "select":
            out.append(("required_missing", ("select", ""), "empty option"))
        elif t == "file":
            out.append(("required_missing", ("file", None), "no file"))
        elif t not in ("radio",):
            out.append(("required_missing", ("fill", ""), "empty"))
    if t in TEXT_TYPES:
        if f.get("maxlength") is not None:
            n, rule = int(f["maxlength"]) + 1, f"len=maxlength+1={int(f['maxlength']) + 1}"
        else:
            n, rule = cfg.validation.long_text_length, f"len={cfg.validation.long_text_length} (default; no maxlength)"
        value = ("a" * max(1, n - 12) + "@example.com") if t == "email" and n > 12 else "a" * n
        out.append(("too_long", ("fill", value), rule))
        if f.get("minlength") and int(f["minlength"]) > 1:
            out.append(("too_short", ("fill", "a" * (int(f["minlength"]) - 1)), f"len=minlength-1={int(f['minlength']) - 1}"))
    if t == "email":
        out.append(("wrong_type", ("fill", "not-an-email"), "no @"))
    elif t == "url":
        out.append(("wrong_type", ("fill", "not a url"), "not a URL"))
    elif t == "tel":
        out.append(("wrong_type", ("fill", "abc"), "letters"))
    elif t in ("number", "range"):
        lo, hi = _num(f.get("min")), _num(f.get("max"))
        step = _num(f.get("step"))
        if lo is not None:
            out.append(("below_min", ("fill", _fmt(lo - (step or 1))), f"min-{_fmt(step or 1)}"))
        if hi is not None:
            out.append(("above_max", ("fill", _fmt(hi + (step or 1))), f"max+{_fmt(step or 1)}"))
        if lo is None and hi is None:
            out.append(("below_min", ("fill", "-1"), "-1 (no min declared)"))
        if f.get("step") in (None, "") or (step is not None and float(step).is_integer()):
            base = lo if lo is not None else 1.0
            out.append(("non_integer", ("fill", _fmt(base + 0.5)), "step mismatch (+0.5)"))
    elif t == "date":
        if f.get("min"):
            out.append(("below_min", ("fill", _shift_date(f["min"], -1)), "min-1 day"))
        if f.get("max"):
            out.append(("above_max", ("fill", _shift_date(f["max"], 1)), "max+1 day"))
    elif t == "file":
        exts = _accept_exts(f.get("accept"))
        if exts:
            bad = ".txt" if ".txt" not in exts else ".exe"
            out.append(("wrong_accept", ("file", _file_payload(bad)), f"{bad} (accept={f.get('accept')})"))
    elif t in TEXT_TYPES:
        if f.get("pattern"):
            for cand in PATTERN_INVALID_CANDIDATES:
                if _pattern_ok(f["pattern"], cand) is False:
                    out.append(("wrong_type", ("fill", cand), "violates pattern"))
                    break
        elif f.get("inputmode") in ("decimal", "numeric") or re.search(
                r"price|amount|qty|quantity|total|cost", (f.get("name") or f.get("label") or "").lower()):
            out.append(("wrong_type", ("fill", "abc"), "letters in a numeric field"))
    return out


def _shift_date(iso: str, days: int) -> str:
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(iso[:10]) + _dt.timedelta(days=days)
        return d.isoformat()
    except ValueError:
        return iso


def plan_probes(form: Dict[str, Any], cfg: DiscoveryConfig) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """-> (probes, skipped). Each probe: {probe, field, fills: {key: action}, value_rule}."""
    fields = [f for f in form.get("fields") or [] if fillable(f)]
    valid: Dict[str, Tuple[Optional[Tuple[str, Any]], str]] = {f["key"]: valid_action(f) for f in fields}
    empty_fills: Dict[str, Tuple[str, Any]] = {}
    for f in fields:
        t = f.get("type")
        if t == "select":
            empty_fills[f["key"]] = ("select", "")
        elif t in ("checkbox", "radio"):
            empty_fills[f["key"]] = ("check", False)
        elif t == "file":
            empty_fills[f["key"]] = ("file", None)
        else:
            empty_fills[f["key"]] = ("fill", "")
    probes = [{"probe": "empty", "field": None, "fills": empty_fills, "value_rule": "all fields cleared"}]
    for f in fields:
        for kind, action, rule in invalid_probes(f, cfg):
            fills = {k: v[0] for k, v in valid.items() if v[0] is not None and k != f["key"]}
            fills[f["key"]] = action
            probes.append({"probe": kind, "field": f["key"], "fills": fills, "value_rule": rule})
    cap = cfg.validation.max_probes_per_form
    skipped = [{"probe": p["probe"], "field": p["field"], "reason": "budget"} for p in probes[cap:]]
    return probes[:cap], skipped


# ── execution ─────────────────────────────────────────────────────────────

def tag_forms(page) -> List[Dict[str, Any]]:
    try:
        return page.evaluate(FORMS_JS, ["tag", None]) or []
    except Exception:
        return []


def _apply(page, key: str, action: Tuple[str, Any]) -> None:
    loc = page.locator(f'[data-mta-field="{key}"]').first
    kind, value = action
    if kind == "fill":
        loc.fill(value, timeout=5_000)
    elif kind == "select":
        if value == "":
            loc.evaluate("el => { el.selectedIndex = [...el.options].findIndex(o => o.value === '');"
                         " el.dispatchEvent(new Event('change', {bubbles: true})); }")
        else:
            loc.select_option(value, timeout=5_000)
    elif kind == "check":
        loc.set_checked(bool(value), timeout=5_000)
    elif kind == "file":
        loc.set_input_files([] if value is None else [value], timeout=5_000)


def _short_path(url: str) -> str:
    import urllib.parse
    p = urllib.parse.urlsplit(url or "")
    return (p.path or "/") + ("?" + p.query if p.query else "")


def run_probe(page, form_fp: str, url_template: str, probe: Dict[str, Any], restore: Callable[[], bool],
              recorder, guard, write_allowed: bool, key_names: Dict[str, str],
              settle: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
    """Execute one probe. Never raises; a failure is recorded in `error`."""
    started = time.monotonic()
    rec: Dict[str, Any] = {"probe": probe["probe"], "field": key_names.get(probe["field"]) if probe["field"] else None,
                           "value_rule": probe["value_rule"], "submitted_via": "", "native": {}, "visible_errors": [],
                           "aria_invalid": [], "focused": None, "network": [], "url_before": "", "url_after": "",
                           "navigated": False, "accepted": False, "error": None, "duration_ms": 0}
    try:
        if not restore():
            rec["error"] = "could not restore the form's page"
            return rec
        forms = tag_forms(page)
        form = next((f for f in forms if form_fingerprint(url_template, f) == form_fp), None)
        if form is None:
            rec["error"] = "form not found after restore"
            return rec
        idx = form["index"]
        pre = {e["text"] for e in page.evaluate(FORMS_JS, ["errors", None]) or []}
        rec["url_before"] = _short_path(page.url)
        for key, action in probe["fills"].items():
            try:
                _apply(page, key, action)
            except Exception as exc:
                if key == probe["field"]:
                    rec["error"] = f"could not set the probed field: {type(exc).__name__}"
                    return rec
        state = page.evaluate(FORMS_JS, ["state", str(idx)]) or {}
        blocked = bool(state.get("any_invalid")) and not state.get("novalidate", True)
        rec["native"] = {"blocked": blocked,
                         "messages": {key_names.get(k, k): v for k, v in (state.get("messages") or {}).items()}}
        recorder.start_probe_log()
        recorder.set_trigger(f"probe {form_fp}:{probe['probe']}" + (f":{rec['field']}" if rec["field"] else ""))
        guard.allow_writes = write_allowed
        url_before_full = page.url
        try:
            if form.get("submit"):
                rec["submitted_via"] = f"click {form['submit'].get('text') or 'submit'}"
                page.locator(f'[data-mta-submit="f{idx}"]').first.click(timeout=5_000, no_wait_after=True)
            else:
                rec["submitted_via"] = "press Enter"
                first = next(iter(probe["fills"]), None)
                page.locator(f'[data-mta-field="{first}"]').first.press("Enter", timeout=5_000)
            page.wait_for_timeout(150)
            if settle is not None:
                settle()
            else:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5_000)
                    page.wait_for_load_state("networkidle", timeout=3_000)
                except Exception:
                    pass
        finally:
            guard.allow_writes = False
        net = recorder.stop_probe_log()
        recorder.drain_json()
        rec["url_after"] = _short_path(page.url)
        rec["network"] = [{"method": n["method"], "path": n["path_template"], "status": n.get("status"),
                           "aborted": bool(n.get("aborted"))} for n in net]
        rec["navigated"] = page.url != url_before_full or any(n["kind"] == "form_submit" for n in net)
        # keys may differ after a server round trip; re-tag and map them back through field *names*
        post_names = {f["key"]: field_name(f) for frm in tag_forms(page) for f in frm.get("fields") or []}
        post = page.evaluate(FORMS_JS, ["errors", None]) or []
        rec["visible_errors"] = [
            {"text": e["text"], "container": e.get("container"), "role": e.get("role"),
             "field": post_names.get(e.get("field")) if e.get("field") else None,
             "attribution": e.get("attribution")}
            for e in post if e["text"] not in pre
        ]
        after_state = page.evaluate(FORMS_JS, ["state", None]) or {}
        rec["aria_invalid"] = sorted({post_names.get(k, k) for k in after_state.get("aria_invalid") or []})
        focused = after_state.get("focused")
        rec["focused"] = post_names.get(focused, focused) if focused else None
        writes = [n for n in net if n["method"] not in ("GET", "HEAD", "OPTIONS") and not n.get("aborted")]
        ok_write = any(n.get("status") is not None and n["status"] < 400 for n in writes)
        rec["accepted"] = bool(not blocked and not rec["visible_errors"] and ok_write)
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        rec["duration_ms"] = int((time.monotonic() - started) * 1000)
    return rec


def observed_messages(field: str, probes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per probe kind: the message the app showed for *field* (visible error first, then native)."""
    out: Dict[str, Any] = {}
    for p in probes:
        if p.get("error"):
            continue
        kind = p["probe"]
        if kind == "empty":
            hits = [e for e in p["visible_errors"] if e.get("field") == field]
            native = (p.get("native") or {}).get("messages", {}).get(field)
            if not hits and not native:
                continue
            kind = "required_missing"
        elif p.get("field") != field:
            continue
        if kind in out:
            continue
        errors = p.get("visible_errors") or []
        mine = [e for e in errors if e.get("field") == field]
        if not mine and len(errors) == 1 and errors[0].get("field") is None:
            mine = [dict(errors[0], attribution="only_error")]
        writes_done = any(n["method"] not in ("GET", "HEAD", "OPTIONS") and not n["aborted"] and n["status"] is not None
                          for n in p.get("network") or [])
        native = (p.get("native") or {}).get("messages", {}).get(field)
        if mine:
            out[kind] = {"text": mine[0]["text"], "source": "server" if writes_done else "client",
                         "attribution": mine[0].get("attribution"), "probe": p["probe"]}
        elif native:
            out[kind] = {"text": native, "source": "native", "attribution": "validity", "probe": p["probe"]}
        elif p.get("accepted"):
            out[kind] = {"text": None, "source": "accepted", "attribution": None, "probe": p["probe"]}
    return out
