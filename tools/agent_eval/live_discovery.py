"""
live_discovery.py — collect first-hand evidence about a deployed agent, for writing a BRD
from the live link alone ("only live link" mode).

Evidence items are numbered [E1], [E2] … so the generated BRD can cite them:
  * rendered pages (Playwright): title, visible text, headings, form fields, buttons, links —
    the landing page plus up to MAX_PAGES same-origin pages linked from it
  * API self-description: /openapi.json, /swagger.json, /docs (FastAPI & co.)
  * the agent's own answers to a few capability questions, if it can be reached — recorded as kind
    "agent_claim": what an agent SAYS it can do is a claim, never evidence of a requirement on its own
Falls back to raw HTML text when a browser can't be launched.

evidence_from_runtime_profile() turns RuntimeDiscoveryAgent's profile (engines/runtime/discovery.py:
authenticated crawl with the project's test account) into the same evidence items, so BrdBuilderAgent
does not crawl the app a second time when that profile exists.

Network access goes through the SSRF guard: http_ssl.guarded_urlopen for HTTP and
engines.runtime.browser.launch_chromium / new_context for the browser.
"""

import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from tools.agent_eval.http_ssl import guarded_urlopen as _urlopen

MAX_PAGES = 4
MAX_TEXT_PER_PAGE = 6_000
CAPABILITY_QUESTIONS = [
    "What can you help me with? Please list your main capabilities.",
    "What are your limitations — what kinds of requests can't you handle?",
    "Show me an example of a typical request you handle well and what you would return.",
]


def _get(url: str, timeout: int = 25) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": "agentic-qa-platform", "Accept": "*/*"})
    try:
        with _urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "ctype": resp.headers.get("Content-Type", ""),
                    "body": resp.read(1_500_000).decode("utf-8", errors="replace")}
    except Exception:
        return None


def _strip_html(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", markup)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", markup))
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", text)).strip()


_PAGE_JS = """() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const txt = el => (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim();
  const q = sel => [...document.querySelectorAll(sel)].filter(vis);
  return {
    title: document.title,
    headings: q('h1,h2,h3').map(txt).filter(Boolean).slice(0, 40),
    fields: q('input:not([type=hidden]),textarea,select').map(el => ({
      label: (el.labels && el.labels[0] ? el.labels[0].innerText : '') || el.getAttribute('aria-label') || el.name || '',
      placeholder: el.getAttribute('placeholder') || '', type: el.type || el.tagName.toLowerCase(),
      required: !!el.required })).slice(0, 60),
    buttons: q('button,[role=button],input[type=submit]').map(txt).filter(Boolean).slice(0, 60),
    links: [...document.querySelectorAll('a[href]')].map(a => ({ text: txt(a), href: a.href })).slice(0, 150),
    text: document.body ? document.body.innerText : ''
  };
}"""


def _render_pages(start_url: str, log: Callable[[str], None]) -> List[Dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    from engines.runtime.browser import launch_chromium, new_context

    origin = urllib.parse.urlsplit(start_url).netloc
    pages: List[Dict[str, Any]] = []
    with sync_playwright() as pw:
        browser = launch_chromium(pw, log)
        try:
            page = new_context(browser, log).new_page()
            queue, seen = [start_url], set()
            while queue and len(pages) < MAX_PAGES:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    page.wait_for_timeout(3_500)  # client-rendered apps (Streamlit/Gradio/React) fill in after load
                    data = page.evaluate(_PAGE_JS)
                except Exception as exc:
                    log(f"Could not render {url}: {type(exc).__name__}")
                    continue
                data["url"] = url
                pages.append(data)
                for link in data.get("links", []):
                    href = urllib.parse.urldefrag(link.get("href") or "")[0]
                    parts = urllib.parse.urlsplit(href)
                    if parts.netloc == origin and parts.scheme in ("http", "https") and href not in seen \
                            and not re.search(r"\.(png|jpe?g|gif|svg|pdf|zip|css|js)$|logout|signout", href, re.I):
                        queue.append(href)
        finally:
            browser.close()
    return pages


def collect_live_evidence(live_url: str, log: Callable[[str], None], chat=None) -> List[Dict[str, str]]:
    """Return [{id, kind, source, content}] — everything observed about the live agent."""
    evidence: List[Dict[str, str]] = []

    def add(kind: str, source: str, content: str) -> None:
        content = content.strip()
        if content:
            evidence.append({"id": f"E{len(evidence) + 1}", "kind": kind, "source": source, "content": content})

    root = _get(live_url)
    is_html = bool(root and ("html" in root["ctype"] or "<html" in root["body"][:2000].lower()))

    if is_html:
        try:
            for p in _render_pages(live_url, log):
                parts = [f"Title: {p.get('title') or ''}"]
                if p.get("headings"):
                    parts.append("Headings: " + " | ".join(p["headings"]))
                if p.get("fields"):
                    parts.append("Input fields: " + "; ".join(
                        f"{f['label'] or f['placeholder'] or f['type']} ({f['type']}{', required' if f['required'] else ''})"
                        for f in p["fields"]))
                if p.get("buttons"):
                    parts.append("Buttons/actions: " + " | ".join(dict.fromkeys(p["buttons"])))
                parts.append("Visible text:\n" + (p.get("text") or "")[:MAX_TEXT_PER_PAGE])
                add("page", p["url"], "\n".join(parts))
        except Exception as exc:
            log(f"Browser rendering unavailable ({type(exc).__name__}) — using the raw HTML instead.")
            add("page", live_url, _strip_html(root["body"])[:MAX_TEXT_PER_PAGE])
    elif root:
        add("http_response", live_url, f"GET {live_url} → HTTP {root['status']} ({root['ctype']})\n{root['body'][:3000]}")

    parsed = urllib.parse.urlsplit(live_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for path in ("/openapi.json", "/swagger.json", "/api/openapi.json", "/v1/openapi.json"):
        doc = _get(base + path)
        if doc and doc["status"] == 200 and doc["body"].lstrip().startswith("{"):
            try:
                spec = json.loads(doc["body"])
                summary = {
                    "title": spec.get("info", {}).get("title"),
                    "description": spec.get("info", {}).get("description"),
                    "paths": {p: {m: {k: op.get(k) for k in ("summary", "description") if op.get(k)}
                                  for m, op in ops.items() if isinstance(op, dict)}
                              for p, ops in (spec.get("paths") or {}).items()},
                    "schemas": list((spec.get("components") or {}).get("schemas", {}).keys())[:40],
                }
                add("api_spec", base + path, json.dumps(summary, indent=1)[:12_000])
                break
            except ValueError:
                continue

    if chat is not None:
        for question in CAPABILITY_QUESTIONS:
            reply = chat.send(question)
            if reply.ok:
                add("agent_claim", f"the agent's own description when asked: {question} "
                    "(a CLAIM, not observed behaviour)", reply.text[:4000])
    log(f"Collected {len(evidence)} piece(s) of evidence from the live app.")
    return evidence


def evidence_from_runtime_profile(profile: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Evidence items from RuntimeDiscoveryAgent's profile; [] when it shows no usable app (login wall, unreachable)."""
    if not isinstance(profile, dict):
        return []
    pages = [p for p in profile.get("pages") or [] if isinstance(p, dict)]
    app_pages = [p for p in pages if p.get("forms") or p.get("buttons") or p.get("headings") or p.get("chat_interface")]
    if not app_pages or profile.get("app_type") in ("Behind login", "Unreachable"):
        return []
    evidence: List[Dict[str, str]] = []

    def add(kind: str, source: str, content: str) -> None:
        content = content.strip()
        if content:
            evidence.append({"id": f"E{len(evidence) + 1}", "kind": kind, "source": source, "content": content})

    summary = [f"App type (from the DOM): {profile.get('app_type') or 'unknown'}"]
    if profile.get("classification_signals"):
        summary.append("Signals: " + "; ".join(map(str, profile["classification_signals"][:6])))
    summary.append(f"Forms: {profile.get('forms', 0)}; downloads/exports: {bool(profile.get('downloads'))}; "
                   f"chat interface: {bool(profile.get('chat_interface'))}; file uploads: {profile.get('file_uploads', 0)}; "
                   f"login required: {bool(profile.get('authentication'))}")
    for flow in (profile.get("user_flows") or [])[:10]:
        if isinstance(flow, dict):
            summary.append(f"User flow '{flow.get('name')}': " + " → ".join(map(str, flow.get("steps") or [])))
    add("app_profile", str(profile.get("live_url") or "runtime discovery"), "\n".join(summary))

    for p in app_pages[:MAX_PAGES * 3]:
        parts = [f"Title: {p.get('title') or ''}"]
        if p.get("headings"):
            parts.append("Headings: " + " | ".join(map(str, p["headings"])))
        for f in p.get("forms") or []:
            if f.get("is_login"):
                parts.append("Login form (the test account signs in here)")
                continue
            fields = []
            for x in (f.get("fields") or [])[:60]:
                label = x.get("label") or x.get("name") or x.get("type") or "field"
                extra = [x.get("type") or "text"] + (["required"] if x.get("required") else [])
                if x.get("options"):
                    extra.append("options: " + ", ".join(map(str, x["options"][:8])))
                fields.append(f"{label} ({', '.join(extra)})")
            parts.append(f"Form ({f.get('field_count', len(fields))} fields, submit: {f.get('submit_button') or 'n/a'}): "
                         + "; ".join(fields))
        if p.get("buttons"):
            parts.append("Buttons/actions: " + " | ".join(dict.fromkeys(map(str, p["buttons"]))))
        dl = p.get("downloads") or {}
        if dl.get("links") or dl.get("buttons"):
            parts.append("Downloads/exports: " + " | ".join(map(str, (dl.get("buttons") or []) + (dl.get("links") or []))))
        if p.get("chat_interface"):
            parts.append("Chat interface: a message box with a send control")
        if p.get("file_uploads"):
            parts.append(f"File upload inputs: {p['file_uploads']}")
        add("page", str(p.get("url") or p.get("path") or "page"), "\n".join(parts))

    calls = [c for c in profile.get("api_calls") or [] if isinstance(c, dict)]
    if calls:
        add("api_calls", "network calls the pages made",
            "\n".join(f"{c.get('method')} {c.get('path')} → {c.get('status')}" for c in calls[:60]))
    return evidence


def render_evidence(evidence: List[Dict[str, str]]) -> str:
    return "\n\n".join(f"[{e['id']}] ({e['kind']} — {e['source']})\n{e['content']}" for e in evidence)
