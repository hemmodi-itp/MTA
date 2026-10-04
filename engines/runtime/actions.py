"""
actions.py — Action Generation Engine.

    inv   = build_inventory(runtime_profile)
    plan  = generate_action_plan(classification, runtime_profile, test_cases, proposals=..., ...)

Turns each BRD-traced test case into an executable, *grounded* list of browser (or HTTP) actions for the
Playwright Executor. Grounded means every target is an element the Runtime Discovery Engine actually saw
on the live app — an inventory entry (field, button, download link, chat box) with a stable id. Nothing is
invented: a step that points at an unknown element is dropped and counted.

Two sources of steps, same output:
  * proposals — per-test steps proposed by Gemini from the inventory (agent prompt), validated here;
  * rules     — deterministic mapping per app class (used when there is no proposal, or it was unusable).
Every plan then goes through the same completion pass: log in first when the app needs it, open the page,
fill required fields the plan left empty (synthetic data; not for negative tests), click the form's trigger,
wait for the result, expect the download (Document Generator), capture evidence, and end with the judged
expectation copied from the test (scored later by Output Validation / Pass-Fail).

Credentials never appear in a plan: `login` is a step the executor resolves with the decrypted test account.
"""

import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ACTIONS = ("login", "goto", "fill", "select", "check", "upload", "click", "send_message", "wait_for", "follow_up",
           "expect_download", "http", "capture", "assert")
UI_CLASSES = {"Chatbot", "Form Application", "Dashboard", "Document Generator", "Workflow System", "Static Website"}
MAX_VALUE = 4000
GENERATION_TIMEOUT_MS = 300_000   # document generators can take minutes, more under load
DEFAULT_TIMEOUT_MS = 30_000
MAX_FLOW_CHECKS = 5

_SUBMIT = re.compile(r"\b(submit|generate|create|send|save|run|start|continue|analy[sz]e|upload|search|ask|go|build|draft)\b", re.I)
_GENERATE = re.compile(r"\b(generate|create|build|draft|compose|produce|convert|run)\b", re.I)
_DOWNLOAD = re.compile(r"\b(download|export|save as|\.docx|\.pdf|\.csv|\.xlsx)\b", re.I)
_SEND = re.compile(r"\b(send|ask|submit|→|➤)\b", re.I)
_APPROVE = re.compile(r"\b(approve|reject|next|back|previous|continue|finish|assign|escalate)\b", re.I)
_LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|auth|register|sign-?up)\b", re.I)
# controls a test must never press: they end the session or destroy data outside the test's scope
# the app's own "fill with sample data" control: the most reliable way to a complete, valid submission
_DEMO = re.compile(r"\b(fill|load|use|insert|try)\b.*\b(demo|sample|example|test)\b.*\b(data|values|content|inputs?)\b|\bautofill\b|"
                   r"\b(demo|sample|example) (data|values)\b", re.I)
_ITEM_PAGE = re.compile(r"/[0-9a-f]{8,}(/|$)|/\d{3,}|/[A-Za-z0-9_-]{20,}|/\d{8}-\d{6}", re.I)
_UNSAFE = re.compile(r"\b(log ?out|sign ?out|logoff|delete (my )?account|deactivate|unsubscribe)\b", re.I)
_NEGATIVE = {"negative", "security", "robustness"}


# ── inventory: what the executor can act on ─────────────────────────────────

def build_inventory(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Stable ids for every actionable element the live app showed (login screens excluded)."""
    elements: Dict[str, Dict[str, Any]] = {}
    forms: Dict[str, Dict[str, Any]] = {}
    chat_boxes: List[str] = []
    pages = [p for p in (profile or {}).get("pages") or []
             if not (_LOGIN_PATH.search(p.get("path") or "") and all(f.get("is_login") for f in p.get("forms") or [{}]))
             # item pages (/runs/<id>, /orders/123…) hold one earlier record's state: never test targets
             and not _ITEM_PAGE.search(p.get("path") or "") and "{id}" not in _route(p.get("path") or "")]
    for pi, p in enumerate(pages):
        path = p.get("path") or "/"
        for fi, f in enumerate(p.get("forms") or []):
            if f.get("is_login"):
                continue
            fid = f"P{pi}F{fi}"
            field_ids = []
            for xi, x in enumerate(f.get("fields") or []):
                eid = f"{fid}I{xi}"
                elements[eid] = {"id": eid, "kind": "field", "page": path, "form": fid, "label": x.get("label") or "",
                                 "name": x.get("name") or "", "type": x.get("type") or "text",
                                 "required": bool(x.get("required")), "options": x.get("options") or None}
                if x.get("revealed_by"):  # a list row: exists only after clicking its "+ Add" button
                    elements[eid]["revealed_by"] = {**x["revealed_by"], "kind": "button", "page": path}
                field_ids.append(eid)
            forms[fid] = {"id": fid, "page": path, "fields": field_ids, "submit_text": f.get("submit_button"),
                          "buttons": f.get("buttons") or []}
            if p.get("chat_interface"):
                chat_boxes += [e for e in field_ids if elements[e]["type"] in ("textarea", "text", "contenteditable")][:1]
        texts, ctxs, seen = p.get("buttons") or [], p.get("button_context") or [], {}
        for bi, text in enumerate(texts):
            if _UNSAFE.search(text):
                continue
            eid = f"P{pi}B{bi}"
            role = ("download" if _DOWNLOAD.search(text) else "send" if p.get("chat_interface") and _SEND.search(text)
                    else "submit" if _SUBMIT.search(text) else "workflow" if _APPROVE.search(text) else "other")
            nth, seen[text] = seen.get(text, 0), seen.get(text, 0) + 1
            elements[eid] = {"id": eid, "kind": "button", "page": path, "text": text, "role": role, "nth": nth,
                             "context": ctxs[bi] if bi < len(ctxs) else ""}
        for e in elements.values():  # nth/context only matter when the same text repeats on a page
            if e["kind"] == "button" and e["page"] == path and seen.get(e["text"], 0) < 2:
                e.pop("nth", None)
                e.pop("context", None)
        for li, href in enumerate((p.get("downloads") or {}).get("links") or []):
            eid = f"P{pi}L{li}"
            elements[eid] = {"id": eid, "kind": "link", "page": path, "href": href, "role": "download"}
    for fid, f in forms.items():  # the form's trigger: its submit button, as an inventory id
        f["submit"] = next((e["id"] for e in elements.values() if e["kind"] == "button" and e["page"] == f["page"]
                            and f["submit_text"] and e["text"] == f["submit_text"]), None)
    return {"elements": elements, "forms": forms, "chat_boxes": chat_boxes,
            "pages": [{"path": p.get("path") or "/", "title": p.get("title"), "headings": (p.get("headings") or [])[:6],
                       "charts": p.get("charts", 0), "tables": p.get("tables", 0)} for p in pages]}


def _route(path: str) -> str:
    from engines.runtime.discovery import _normalise
    return _normalise(path)


def inventory_for_prompt(inv: Dict[str, Any], limit: int = 320) -> List[Dict[str, Any]]:
    """Compact inventory rows for the LLM (no hrefs beyond the path)."""
    rows = []
    for e in list(inv["elements"].values())[:limit]:
        r = {k: v for k, v in e.items() if (v not in (None, "", False) and k not in ("href", "revealed_by"))
             or (k == "nth" and v == 0)}
        if e.get("revealed_by"):
            r["list_row"] = True  # the engine clicks the list's "+ Add" before filling it
        rows.append(r)
    return rows


# ── synthetic test data for fields a test does not set ──────────────────────

def synthetic_value(el: Dict[str, Any], hint: str = "") -> Optional[str]:
    t = el.get("type") or "text"
    label = re.sub(r"\(required\)|\*", "", f"{el.get('label', '')} {el.get('name', '')}", flags=re.I).strip().lower()
    if t in ("checkbox", "radio"):
        return "true"
    if t == "select" or el.get("options"):
        opts = [o for o in (el.get("options") or []) if o and not re.match(r"^(select|choose|--|pick)", o, re.I)]
        return opts[0] if opts else None
    if t == "file":
        return None  # uploads need a fixture; the executor supplies one per test
    if t == "email" or "email" in label:
        return "qa.bot+aqp@example.com"
    if t == "tel" or re.search(r"phone|mobile|tel", label):
        return "+1 555 010 0199"
    if t == "url" or re.search(r"\burl\b|website|link", label):
        return "https://example.com"
    if t == "number" or re.search(r"\b(amount|count|number|qty|quantity|age|budget|years?)\b", label):
        return "10"
    if t == "date" or "date" in label:
        return "2026-10-15"
    if t == "password":
        return None
    if re.search(r"\bname\b", label) and re.search(r"project|product|app|company|org", label):
        return "MTA Evaluation Project"
    if re.search(r"first.?name|last.?name|full.?name|\bname\b", label):
        return "Alex Tester"
    if re.search(r"company|organi[sz]ation|client", label):
        return "Example Corp"
    if re.search(r"acronym|abbreviation|\bcode\b|doc(ument)? ?id|\bid\b|\bkey\b|prefix", label):
        return "MTA"
    if re.search(r"tech(nology)?\s*stack|technolog|framework|platform", label):
        return "Python, FastAPI, React, PostgreSQL"
    if re.search(r"\bsteps?\b|flow|process|workflow", label):
        return "1. The user submits a request. 2. The system validates and processes it. 3. The result is shown and stored."
    if re.search(r"scope|feature|requirement|deliverable", label):
        return "Online booking; automated reminders; an admin report of bookings per week."
    if re.search(r"audience|stakeholder|user|persona", label):
        return "Operations managers and front-desk staff"
    if t in ("textarea", "contenteditable"):
        subject = re.sub(r"\(required\)|\*", "", el.get("label") or el.get("name") or "this field", flags=re.I).strip()
        return (hint or f"Sample {subject.lower()} for an automated acceptance test: a small team needs a "
                         f"web tool to track requests, approvals and reports.")[:MAX_VALUE]
    subject = re.sub(r"\(required\)|\*", "", el.get("label") or el.get("name") or "value", flags=re.I).strip()
    return (hint or f"Sample {subject.lower()}")[:200]


# ── proposal validation ─────────────────────────────────────────────────────

def validate_steps(raw_steps: Sequence[Dict[str, Any]], inv: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    """Keep only steps whose action is known and whose element exists and suits the action."""
    els, out, dropped = inv["elements"], [], 0
    for s in raw_steps or []:
        action = str(s.get("action") or "").strip()
        el = els.get(str(s.get("element_id") or "").strip())
        value = s.get("value")
        value = None if value is None else str(value)[:MAX_VALUE]
        ok = (
            (action == "fill" and el and el["kind"] == "field" and el["type"] not in ("select", "checkbox", "radio", "file")
             and value is not None)
            or (action == "select" and el and el["kind"] == "field" and (el["type"] == "select" or el["options"])
                and value is not None and (not el["options"] or value in el["options"]))
            or (action == "check" and el and el["kind"] == "field" and el["type"] in ("checkbox", "radio"))
            or (action == "upload" and el and el["kind"] == "field" and el["type"] == "file")
            or (action == "click" and el and el["kind"] in ("button", "link"))
            or (action == "send_message" and el and el["id"] in inv["chat_boxes"] and value)
            or (action == "expect_download" and el and el.get("role") == "download")
        )
        if not ok:
            dropped += 1
            continue
        out.append({"action": action, "target": _target(el), **({"value": value} if value is not None else {})})
    return out, dropped


def _target(el: Dict[str, Any]) -> Dict[str, Any]:
    """Everything the executor needs to locate the element (label → name → placeholder/text fallbacks)."""
    keep = ("id", "kind", "page", "label", "name", "type", "text", "href", "role", "nth", "context")
    return {k: el[k] for k in keep if el.get(k) not in (None, "")}


# ── rule-based mapping per app class ────────────────────────────────────────

def _main_form(inv: Dict[str, Any], prefer_generate: bool) -> Optional[Dict[str, Any]]:
    forms = list(inv["forms"].values())
    if not forms:
        return None
    def rank(f):
        sub = f.get("submit_text") or ""
        return (bool(prefer_generate and _GENERATE.search(sub)), len(f["fields"]))
    return max(forms, key=rank)


def _best_free_text(form: Dict[str, Any], inv: Dict[str, Any], text: str) -> Optional[Dict[str, Any]]:
    els = [inv["elements"][e] for e in form["fields"]]
    free = [e for e in els if e["type"] in ("textarea", "contenteditable", "text") and not e.get("options")]
    if not free:
        return None
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    def score(e):
        lab = f"{e['label']} {e['name']}".lower()
        return (len(words & set(re.findall(r"[a-z]{4,}", lab))), e["type"] in ("textarea", "contenteditable"))
    return max(free, key=score)


def rule_steps(test: Dict[str, Any], app_class: str, inv: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Deterministic steps for one test; returns (steps, unmappable_reason)."""
    els, text = inv["elements"], str(test.get("input") or "")
    if app_class == "Chatbot" or (inv["chat_boxes"] and not inv["forms"]):
        if not inv["chat_boxes"]:
            return [], "no chat box was found on the live app"
        box = els[inv["chat_boxes"][0]]
        return [{"action": "send_message", "target": _target(box), "value": text[:MAX_VALUE]}], None
    if app_class in ("Form Application", "Document Generator", "Workflow System"):
        form = _main_form(inv, prefer_generate=app_class == "Document Generator")
        if not form:
            return [], "no input form was found on the live app"
        steps = []
        main = _best_free_text(form, inv, text)
        if main and text:
            steps.append({"action": "fill", "target": _target(main), "value": text[:MAX_VALUE]})
        if app_class == "Workflow System":
            steps += [{"action": "click", "target": _target(e)} for e in els.values()
                      if e["kind"] == "button" and e["role"] == "workflow" and e["page"] == form["page"]][:2]
        if not steps and test.get("variant_type") in _NEGATIVE:
            steps = [{"action": "goto", "url": form["page"]}]  # submit the form without the data it requires
        return steps, None
    if app_class == "Dashboard":
        page = next((p for p in inv["pages"] if p["charts"] or p["tables"]), inv["pages"][0] if inv["pages"] else None)
        if not page:
            return [], "no dashboard page was found"
        return [{"action": "goto", "url": page["path"]},
                {"action": "assert", "kind": "visible", "value": "chart or table", "page": page["path"]}], None
    if app_class == "Static Website":
        page = inv["pages"][0] if inv["pages"] else None
        return ([{"action": "goto", "url": page["path"]}] if page else []), None if page else "no page was found"
    return [], f"no UI mapping for a {app_class}"


def http_steps(test: Dict[str, Any], endpoints: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """REST API: send the test input to the app's documented endpoint — a path on the live app's own origin
    (endpoint paths come from an LLM reading the repo, so absolute or scheme-relative URLs are refused)."""
    ep = next((e for e in endpoints if isinstance(e, dict) and _relative_path(e.get("path"))), None)
    if not ep:
        return [], "no HTTP endpoint on the live app's origin is known for the app"
    field = ep.get("input_field") or "message"
    method = (ep.get("method") or "POST").upper()
    if method not in ("GET", "POST", "PUT", "PATCH"):
        method = "POST"
    return [{"action": "http", "method": method, "path": _relative_path(ep["path"]),
             "body": {field: str(test.get("input") or "")[:MAX_VALUE]}, "expect_status": "2xx"}], None


def _relative_path(path: Any) -> Optional[str]:
    """An endpoint path usable on the live origin: starts with one '/', no scheme, host or whitespace tricks."""
    p = str(path or "").strip()
    if not p.startswith("/") or p.startswith("//") or "://" in p or "\\" in p or any(ch.isspace() for ch in p):
        return None
    return p[:300]


# ── completion pass ─────────────────────────────────────────────────────────

def complete(steps: List[Dict[str, Any]], test: Dict[str, Any], app_class: str, inv: Dict[str, Any],
             needs_login: bool) -> List[Dict[str, Any]]:
    els = inv["elements"]
    negative = test.get("variant_type") in _NEGATIVE
    after = [s for s in steps if s.get("phase") == "after"]       # acts on the generated result (export, revise…)
    steps = [s for s in steps if s.get("phase") != "after"]
    http = any(s["action"] == "http" for s in steps)
    body = [s for s in steps if s["action"] not in ("login", "goto")] if not http else list(steps)
    pages = [s.get("target", {}).get("page") for s in body if s.get("target")]
    page = next((p for p in pages if p), None) or next((s["url"] for s in steps if s["action"] == "goto"), None)
    out: List[Dict[str, Any]] = []
    if needs_login and not http:
        out.append({"action": "login"})
    if page and not http:
        out.append({"action": "goto", "url": page})

    touched = {s["target"]["id"] for s in body if s.get("target", {}).get("id")}
    form = next((inv["forms"][els[i]["form"]] for i in touched if i in els and els[i].get("form")), None)
    if form is None and app_class in ("Form Application", "Document Generator", "Workflow System") and not http:
        form = _main_form(inv, prefer_generate=app_class == "Document Generator")
        if form and not page:
            out.append({"action": "goto", "url": form["page"]})
    fills = [s for s in body if s["action"] in ("fill", "select", "check", "upload")]
    rest = [s for s in body if s not in fills]
    demo = None
    text_fields = [f for f in (form or {}).get("fields", []) if els[f]["type"] not in ("checkbox", "radio", "file")]
    covered = len({s["target"]["id"] for s in fills if s.get("target", {}).get("id") in text_fields})
    if form and not negative and text_fields and covered < 0.8 * len(text_fields):
        # the plan does not describe the whole form: start from the app's own demo data (if it has a control for it)
        # so the submission is complete; the test's own values then overwrite it. Optional: skipped if not there.
        demo = next((e for e in els.values() if e["kind"] == "button" and e["page"] == form["page"] and _DEMO.search(e["text"])), None)
        if demo:
            out.append({"action": "click", "target": _target(demo), "synthetic": True, "purpose": "prefill demo data",
                        "optional": True})
    out += fills
    if form and not negative and not demo:  # complete required fields the test didn't set (not on top of demo data:
        # mixing generic filler into the demo scenario would make the input incoherent)
        for fid in form["fields"]:
            el = els[fid]
            if fid in touched or not el["required"]:
                continue
            step = _fill_step(el)
            if step:
                out.append(step)
    trigger_clicked = any(s["action"] in ("click", "send_message") and s["target"].get("role") in ("submit", "send", None)
                          for s in rest if s.get("target")) or any(s["action"] == "send_message" for s in rest)
    out += [s for s in rest if s["action"] != "expect_download"]
    generating = app_class == "Document Generator" or bool(form and _GENERATE.search(form.get("submit_text") or ""))
    if form and not trigger_clicked and form.get("submit"):
        out.append({"action": "click", "target": _target(els[form["submit"]])})
        trigger_clicked = True
    if trigger_clicked or http:
        out.append({"action": "wait_for", "kind": "response" if http else "settled",
                    "timeout_ms": GENERATION_TIMEOUT_MS if generating or http else DEFAULT_TIMEOUT_MS})
    for s in after:
        out.append({k: v for k, v in s.items() if k != "phase"})
        if s["action"] == "follow_up":  # a revision / follow-up request regenerates too
            out.append({"action": "wait_for", "kind": "settled", "timeout_ms": GENERATION_TIMEOUT_MS})
    downloads = [s for s in rest if s["action"] == "expect_download"] + \
        [s for s in out if s["action"] == "expect_download" and s not in rest]
    out = [s for s in out if s["action"] != "expect_download"]
    if not downloads and app_class == "Document Generator" and not negative and not http:
        dl = next((e for e in els.values() if e.get("role") == "download" and (not page or e["page"] == page)), None) \
            or next((e for e in els.values() if e.get("role") == "download"), None)
        if dl:
            downloads = [{"action": "expect_download", "target": _target(dl)}]
        else:  # export controls often appear only after generating: the executor finds them at run time
            downloads = [{"action": "expect_download", "target": {"kind": "auto", "role": "download", "page": page}}]
    out += downloads
    out.append({"action": "capture", "what": ["screenshot", "dom_text"] + (["reply"] if any(
        s["action"] == "send_message" for s in out) else []) + (["download"] if downloads else []) + (["response"] if http else [])})
    out.append({"action": "assert", "kind": "judge", "expectation": test.get("expected_behavior") or "",
                "pass_criteria": test.get("pass_criteria") or []})
    out = _insert_row_adds(out, els)
    for i, s in enumerate(out, 1):
        s["n"] = i
    return out


def _insert_row_adds(steps: List[Dict[str, Any]], els: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Before filling a list-row field, click the "+ Add" button that creates its row (once per button)."""
    out, added = [], set()
    for s in steps:
        el = els.get((s.get("target") or {}).get("id") or "")
        rb = (el or {}).get("revealed_by")
        if rb and s["action"] in ("fill", "select", "check"):
            key = (rb.get("text"), rb.get("nth"), rb.get("context"))
            if key not in added:
                added.add(key)
                out.append({"action": "click", "target": {k: v for k, v in rb.items() if v not in (None, "")} | {"nth": rb.get("nth", 0)},
                            "purpose": "add a list row", "synthetic": bool(s.get("synthetic"))})
        out.append(s)
    return out


_AFTER_EXPORT = re.compile(r"\b(export|download|docx|pdf|word|one.?pager|file)\b", re.I)
_AFTER_REVISE = re.compile(r"\b(revis\w*|change request|regenerat\w*|iterat\w*|refine|update the|modify|edit)\b", re.I)
_AFTER_PREVIEW = re.compile(r"\b(preview|render\w*|side.by.side|display\w*|diagram)\b", re.I)
_AFTER_HISTORY = re.compile(r"\b(history|historical|versions?|previous runs?|list (of )?runs|immutable)\b", re.I)
_AFTER_TIMING = re.compile(r"\b(latency|response time|execution time|performance|completes? (with)?in|"
                           r"(under|within|less than) \d+\s*(s|sec|secs|seconds|minutes?))\b", re.I)


def generate_then_act(test: Dict[str, Any], app_class: str, inv: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """For a Document Generator, behaviour that only exists after generating (export, revise, preview, history)
    becomes: fill the main form, generate, then act on the result. None when it does not apply."""
    if app_class != "Document Generator" or test.get("variant_type") in _NEGATIVE:
        return None
    form = _main_form(inv, prefer_generate=True)
    if not form or not form.get("submit"):
        return None
    text = " ".join(str(test.get(k) or "") for k in ("title", "input", "expected_behavior", "area"))
    steps: List[Dict[str, Any]] = [{"action": "goto", "url": form["page"]}]
    matched = False
    if _AFTER_REVISE.search(text):
        matched = True
        request = _change_request(str(test.get("input") or "")) or str(test.get("input") or "")[:500]
        steps.append({"action": "follow_up", "kind": "text_input", "value": request, "phase": "after",
                      "known_labels": [inv["elements"][f]["label"] for f in form["fields"]]})
    if _AFTER_HISTORY.search(text):
        hist = next((p["path"] for p in inv["pages"] if re.search(r"histor|runs|versions|dashboard", p["path"], re.I)), None)
        if hist:
            steps.append({"action": "goto", "url": hist, "phase": "after"})
            matched = True
    if _AFTER_EXPORT.search(text):
        steps.append({"action": "expect_download", "target": {"kind": "auto", "role": "download", "page": form["page"]},
                      "phase": "after"})
        matched = True
    # preview tests: the result page itself is captured and judged; timing tests: the generation is timed by the
    # executor and checked by Output Validation's time-limit check
    matched = matched or bool(_AFTER_PREVIEW.search(text)) or bool(_AFTER_TIMING.search(text))
    return steps if matched else None


def _change_request(text: str) -> Optional[str]:
    """The change request inside an API-style test input, e.g. POST …/revise {"change_request": "…"}."""
    m = re.search(r'"(change_request|request|instruction|feedback|prompt)"\s*:\s*"([^"]{5,})"', text)
    return m.group(2) if m else None


def _fill_step(el: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A synthetic-data step for one field (None when no safe value exists, e.g. file or password)."""
    v = synthetic_value(el)
    if v is None:
        return None
    if el["type"] in ("checkbox", "radio"):
        return {"action": "check", "target": _target(el), "synthetic": True}
    act = "select" if (el["type"] == "select" or el["options"]) else "fill"
    return {"action": act, "target": _target(el), "value": v, "synthetic": True}


# ── whole plan ──────────────────────────────────────────────────────────────

def generate_action_plan(classification: Optional[Dict[str, Any]], profile: Optional[Dict[str, Any]],
                         test_cases: Sequence[Dict[str, Any]], proposals: Optional[Dict[str, Dict[str, Any]]] = None,
                         has_credentials: bool = False, endpoints: Sequence[Dict[str, Any]] = (),
                         log: Callable[..., None] = lambda *a, **k: None) -> Dict[str, Any]:
    app_type = (classification or {}).get("app_type") or (profile or {}).get("app_type") or "Unknown"
    inv = build_inventory(profile)
    classes = effective_classes(app_type, (classification or {}).get("components") or [], inv, endpoints)
    primary = classes[0]
    needs_login = bool(((profile or {}).get("login") or {}).get("succeeded"))
    proposals = proposals or {}
    base = {"app_type": app_type, "strategy": (classification or {}).get("testing_strategy") or [],
            "requires_login": needs_login, "inventory_size": len(inv["elements"])}

    api_only = primary == "REST API"
    login = (profile or {}).get("login") or {}
    if not api_only and login.get("attempted") and not login.get("succeeded") and (profile or {}).get("needs_credentials"):
        return {**base, "status": "blocked", "plans": [],
                "reason": f"Login with the test account failed ({login.get('error')}), so MTA could not reach the app's pages. "
                          "Check the account's email and password (try them on the live app's login page) and re-run.",
                "counts": {"tests": len(test_cases), "ready": 0, "unmappable": 0, "blocked": len(test_cases)}}
    if not api_only and (profile or {}).get("needs_credentials") and not has_credentials:
        return {**base, "status": "blocked", "plans": [],
                "reason": "The live app is behind a login and no test account is configured; add one to the project.",
                "counts": {"tests": len(test_cases), "ready": 0, "unmappable": 0, "blocked": len(test_cases)}}
    if not api_only and not inv["elements"]:
        return {**base, "status": "blocked", "plans": [],
                "reason": "Runtime discovery found nothing to act on (no forms, buttons or chat box).",
                "counts": {"tests": len(test_cases), "ready": 0, "unmappable": 0, "blocked": len(test_cases)}}

    plans, ungrounded, llm_used = [], 0, 0
    for t in test_cases:
        cls = _class_for(t, classes, inv)
        steps, reason, source = [], None, "rules"
        prop = proposals.get(t.get("code"))
        if prop is not None and not api_only:
            if prop.get("applicable") is False:
                reason, source = prop.get("reason") or "not testable through the UI", "llm"
            else:
                steps, dropped = validate_steps(prop.get("steps") or [], inv)
                ungrounded += dropped
                if steps:
                    source, llm_used = "llm", llm_used + 1
        if not steps and reason is None:
            use_http = api_only or (t.get("execution") == "api" and any(
                _relative_path((e or {}).get("path")) for e in endpoints if isinstance(e, dict)))
            steps, reason = http_steps(t, endpoints) if use_http else rule_steps(t, cls, inv)
            if not steps and reason is None:
                # nothing in the test names an element the rules can find: say so instead of a padded plan
                reason = "no discovered element matches this test (needs AI mapping, or the feature is not on the app)"
        if reason and not steps and not api_only:
            follow = generate_then_act(t, cls, inv)
            if follow is not None:
                steps, reason, source = follow, None, "rules"
        if reason and not steps:
            plans.append(_plan(t, cls, "unmappable", [], source, reason))
            continue
        plans.append(_plan(t, cls, "ready", complete(steps, t, cls, inv, needs_login), source))

    exercised = {_form_of(p, inv) for p in plans if p["status"] == "ready"}
    plans += flow_checks(inv, primary, needs_login, skip_forms=exercised) if not api_only else []
    ready = sum(1 for p in plans if p["status"] == "ready" and p["scored"])
    unmappable = sum(1 for p in plans if p["status"] == "unmappable")
    if ungrounded:
        log(f"Dropped {ungrounded} proposed step(s) that pointed at elements the live app does not have.", "warning")
    return {**base, "status": "ready" if ready else "blocked" if not plans else "partial", "plans": plans,
            "reason": None if ready else "No test could be mapped onto the live app's elements.",
            "counts": {"tests": len(test_cases), "ready": ready, "unmappable": unmappable, "blocked": 0,
                       "flow_checks": sum(1 for p in plans if not p["scored"]), "llm_mapped": llm_used,
                       "ungrounded_steps_dropped": ungrounded}}


def effective_classes(app_type: str, components: Sequence[str], inv: Dict[str, Any],
                      endpoints: Sequence[Dict[str, Any]] = ()) -> List[str]:
    """The classes the rules can act on. A Hybrid app uses its components; an unknown or unclassified app is
    mapped from what discovery found (chat box -> Chatbot, form -> Form Application, documented endpoint and no UI
    -> REST API, otherwise Static Website) instead of leaving every test unmappable."""
    known = UI_CLASSES | {"REST API"}
    classes = [c for c in (components or [app_type]) if c in known]
    if classes:
        return classes
    if inv.get("chat_boxes"):
        classes.append("Chatbot")
    if inv.get("forms"):
        classes.append("Form Application")
    if not classes and not inv.get("elements") and any(
            _relative_path((e or {}).get("path")) for e in endpoints if isinstance(e, dict)):
        classes.append("REST API")
    return classes or ["Static Website"]


def _class_for(test: Dict[str, Any], classes: List[str], inv: Dict[str, Any]) -> str:
    """For a Hybrid app: the component whose surface best fits the test (chat box vs form vs dashboard)."""
    if len(classes) == 1:
        return classes[0]
    text = f"{test.get('title', '')} {test.get('input', '')} {test.get('area', '')}".lower()
    if "Chatbot" in classes and re.search(r"\b(chat|ask|reply|respond|answer|conversation|message)\b", text):
        return "Chatbot"
    if "Dashboard" in classes and re.search(r"\b(chart|dashboard|metric|report|graph|analytics|kpi)\b", text):
        return "Dashboard"
    ui = [c for c in classes if c in UI_CLASSES and c not in ("Chatbot", "Dashboard")]
    return ui[0] if ui else classes[0]


def _plan(t: Dict[str, Any], cls: str, status: str, steps: List[Dict], source: str, reason: Optional[str] = None) -> Dict[str, Any]:
    return {"plan_id": f"AP-{t.get('code') or 'X'}", "test_id": t.get("id"), "test_code": t.get("code"),
            "criterion_code": t.get("criterion_code"), "requirement_ref": t.get("requirement_ref"),
            "title": t.get("title"), "variant": t.get("variant_type"), "class": cls, "kind": "brd_test", "scored": True,
            "status": status, "source": source, "reason": reason, "steps": steps}


def _form_of(plan: Dict[str, Any], inv: Dict[str, Any]) -> Optional[str]:
    for s in plan.get("steps") or []:
        el = inv["elements"].get((s.get("target") or {}).get("id") or "")
        if el and el.get("form"):
            return el["form"]
    return None


def flow_checks(inv: Dict[str, Any], primary: str, needs_login: bool, skip_forms=frozenset()) -> List[Dict[str, Any]]:
    """One unscored end-to-end check per discovered flow that no BRD test already exercises."""
    out = []
    for f in [f for f in inv["forms"].values() if f["id"] not in skip_forms][:MAX_FLOW_CHECKS]:
        pseudo = {"code": f"FLOW-{f['id']}", "title": f"Flow check: submit the form on {f['page']}",
                  "variant_type": "positive", "input": "",
                  "expected_behavior": "The form submits without an error and the app shows its result"
                                       + (" and offers the generated file" if primary == "Document Generator" else ""),
                  "pass_criteria": ["no error message", "a result or confirmation is shown"]}
        # fill values only: ticking every checkbox ("not applicable", "auto-generate"…) would change what the form does
        steps = [s for s in (_fill_step(inv["elements"][e]) for e in f["fields"]) if s and s["action"] != "check"]
        for s in steps:  # a flow check must change something: pick the last option, not the (usually pre-selected) first
            opts = [o for o in (s["target"].get("id") and inv["elements"][s["target"]["id"]].get("options") or [])
                    if o and not re.match(r"^(select|choose|--|pick)", o, re.I)]
            if s["action"] == "select" and len(opts) > 1:
                s["value"] = opts[-1]
        p = _plan(pseudo, primary if primary != "Hybrid Application" else "Form Application", "ready",
                  complete(steps, pseudo, "Document Generator" if primary == "Document Generator" else "Form Application",
                           inv, needs_login), "rules")
        p.update(kind="flow_check", scored=False, plan_id=f"AP-FLOW-{f['id']}", test_code=None)
        out.append(p)
    for box in inv["chat_boxes"][:1]:
        pseudo = {"code": "FLOW-CHAT", "title": "Flow check: the chat replies", "variant_type": "positive",
                  "expected_behavior": "The assistant returns a non-empty, relevant reply", "pass_criteria": ["reply received"]}
        p = _plan(pseudo, "Chatbot", "ready", complete([{"action": "send_message", "target": _target(inv["elements"][box]),
                                                         "value": "Hello! What can you help me with?"}], pseudo, "Chatbot",
                                                       inv, needs_login), "rules")
        p.update(kind="flow_check", scored=False, plan_id="AP-FLOW-CHAT", test_code=None)
        out.append(p)
    return out

