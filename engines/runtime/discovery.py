"""
discovery.py — Runtime Discovery Engine: open a live deployment and describe what a user can do there.

    profile = discover(live_url, known_pages=["/new", "/runs"], known_api_routes=["POST /api/generate"])

Deterministic (Playwright + DOM inspection, no LLM). For the landing page and up to MAX_PAGES
same-origin pages (links found while crawling, plus page routes known from the repository's
knowledge graph) it records:

  * forms — real <form>s AND "virtual forms" (a group of inputs with a submit-like button but no
    <form> element, the usual shape of React/Next.js apps), with every field's label, type and
    whether it is required;
  * buttons, links, downloads (download attributes, file links, Export/Download buttons),
    file uploads, chat interfaces (editable textbox + send control / chat-like log regions);
  * authentication signals (password fields, login pages, redirects to /login, API 401/403s);
  * network calls the page makes (method, path, status) — the app's real API surface;
  * framework markers (Next.js, Streamlit, Gradio, …).

From those it derives candidate user flows and a preliminary app_type (the App Classification
Engine refines it). Output matches the Runtime Discovery contract:

    {"app_type": "Document Generator", "forms": 3, "buttons": 8, "downloads": true,
     "chat_interface": false, "authentication": false, ...details}
"""

import re
import time
import urllib.parse
from typing import Any, Callable, Dict, Iterable, List, Optional

MAX_PAGES = 12
MAX_NAVIGATIONS = 40               # attempts incl. failed / duplicate pages — the crawl can never loop unbounded
DISCOVERY_BUDGET_S = 600           # whole crawl (login excluded); the run's step deadline is the backstop
NAV_TIMEOUT_MS = 45_000
WAKE_TIMEOUT_MS = 120_000          # first request to a scale-to-zero host can take over a minute
LOGIN_FORM_TIMEOUT_MS = 25_000     # client-rendered login forms appear after hydration
LOGIN_RESULT_TIMEOUT_MS = 25_000
SETTLE_MS = 3_000
RENDER_WAIT_S = 30                 # client-rendered pages: wait until the content has actually rendered
RECHECK_WAIT_S = 75                # a page that should have a form but showed none gets one longer look

_AUTH_WORDS = re.compile(r"\b(log ?in|sign ?in|sign ?up|register|forgot password|authenticate)\b", re.I)
_DOWNLOAD_WORDS = re.compile(r"\b(download|export|save as|\.docx|\.pdf|\.csv|\.xlsx)\b", re.I)
_SUBMIT_WORDS = re.compile(r"\b(submit|generate|create|send|save|run|start|continue|next|analy[sz]e|upload|search|ask|go)\b", re.I)
_CHAT_WORDS = re.compile(r"\b(chat|message|ask (me|anything)|type your|conversation|assistant)\b", re.I)
_REQUIRED_LABEL = re.compile(r"\(required\)|\brequired\b\s*$|\*\s*$", re.I)
_SKIP_LINK = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|docx?|xlsx?|csv|css|js|map)(\?|$)|logout|log-out|sign-?out|"
                        r"mailto:|tel:|javascript:|/(delete|remove|destroy|deactivate|unsubscribe|reset|revoke|cancel)\b|"
                        r"[?&](action|op)=(delete|remove|destroy)", re.I)

# Cheap per-poll readiness probe: [interactive controls in the main area, text length, busy indicator / wording].
_READY_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const nav = el => !!el.closest('nav,aside,header,[role=navigation],[class*=sidebar i]');
  const controls = [...document.querySelectorAll('input:not([type=hidden]),textarea,select,[contenteditable=true],button,[role=button]')]
    .filter(el => vis(el) && !nav(el)).length;
  const text = (document.body && document.body.innerText) || '';
  const busy = [...document.querySelectorAll('[aria-busy=true],[role=progressbar],[class*=spinner i],[class*=loading i],[class*=skeleton i]')]
    .some(vis) || /^\s*(loading|please wait)/im.test(text);
  const headings = [...document.querySelectorAll('main h1,main h2,h1,h2')].filter(el => vis(el) && !nav(el)).length;
  return [controls, text.length, busy, headings];
}"""


def _wait_for_render(page, max_s: float = RENDER_WAIT_S) -> Dict[str, Any]:
    """Wait until a client-rendered page shows its content: no busy indicator and the main area's controls / text
    unchanged across two polls. Pages that look empty (no controls, no headings) keep being polled until max_s,
    because SPAs fill the main area only after their API calls return (slow on a cold backend)."""
    t0 = time.monotonic()
    last, stable = None, 0
    probe = [0, 0, True, 0]
    while time.monotonic() - t0 < max_s:
        try:
            probe = page.evaluate(_READY_JS)
        except Exception:
            probe = [0, 0, True, 0]
        controls, length, busy, headings = probe
        key = (controls, length // 50)
        stable = stable + 1 if key == last and not busy else 0
        last = key
        looks_empty = controls == 0 and headings == 0
        if stable >= 2 and (not looks_empty or time.monotonic() - t0 > max_s / 2):
            break
        page.wait_for_timeout(1_500)
    return {"waited_s": round(time.monotonic() - t0, 1), "controls": probe[0], "busy": bool(probe[2])}


# Runs inside the page; returns everything about one page in one round-trip.
_PAGE_SCAN_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const txt = el => ((el.innerText || el.value || '').trim() || el.getAttribute('aria-label') || el.getAttribute('title') || '').slice(0, 120);
  const labelOf = el => {
    if (el.labels && el.labels[0]) { const c = el.labels[0].cloneNode(true);  // the label's own words, not a nested control's
      c.querySelectorAll('input,select,textarea,option,button').forEach(n => n.remove());
      return (c.textContent || '').replace(/\s+/g, ' ').trim(); }
    const id = el.getAttribute('aria-labelledby'); if (id && document.getElementById(id)) return document.getElementById(id).innerText.trim();
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || el.id || '';
  };
  const fieldInfo = el => ({
    label: labelOf(el).slice(0, 120), name: el.getAttribute('name') || '', tag: el.tagName.toLowerCase(),
    type: (el.getAttribute('type') || (el.tagName === 'TEXTAREA' ? 'textarea' : el.tagName === 'SELECT' ? 'select' : el.isContentEditable ? 'contenteditable' : 'text')).toLowerCase(),
    required: !!(el.required || el.getAttribute('aria-required') === 'true'),
    readonly: !!(el.readOnly || el.disabled || el.getAttribute('aria-readonly') === 'true'),
    options: el.tagName === 'SELECT' ? [...el.options].slice(0, 12).map(o => o.text.trim()) : undefined,
  });
  const inputs = [...document.querySelectorAll('input:not([type=hidden]),textarea,select,[contenteditable=true],[role=textbox]')].filter(vis);
  const buttons = [...document.querySelectorAll('button,[role=button],input[type=submit],input[type=button]')].filter(vis);
  const forms = [...document.querySelectorAll('form')].filter(vis).map(f => ({
    kind: 'form', action: f.getAttribute('action') || '', method: (f.getAttribute('method') || 'get').toLowerCase(),
    fields: [...f.querySelectorAll('input:not([type=hidden]),textarea,select,[contenteditable=true]')].filter(vis).map(fieldInfo),
    buttons: [...f.querySelectorAll('button,input[type=submit]')].filter(vis).map(txt).filter(Boolean),
  }));
  // virtual forms: inputs outside any <form>, grouped under their nearest shared container
  const loose = inputs.filter(el => !el.closest('form'));
  let virtual = [];
  if (loose.length) {
    const root = loose.reduce((acc, el) => { let a = acc; while (a && !a.contains(el)) a = a.parentElement; return a; }, loose[0].parentElement) || document.body;
    const btns = [...root.querySelectorAll('button,[role=button],input[type=submit]')].filter(vis).map(txt).filter(Boolean);
    virtual = [{ kind: 'virtual', action: '', method: '', fields: loose.map(fieldInfo), buttons: btns.slice(0, 20) }];
  }
  const links = [...document.querySelectorAll('a[href]')].map(a => ({ text: txt(a), href: a.href, download: a.hasAttribute('download') })).slice(0, 200);
  const logRegions = document.querySelectorAll('[role=log],[class*=chat i],[data-testid*=chat i],[id*=chat i]').length;
  return {
    title: document.title, url: location.href,
    headings: [...document.querySelectorAll('h1,h2,h3')].filter(vis).map(txt).filter(Boolean).slice(0, 30),
    forms: forms.concat(virtual), inputs: inputs.map(fieldInfo),
    buttons: buttons.map(b => ({ text: txt(b), type: (b.getAttribute('type') || '').toLowerCase(), disabled: !!b.disabled,
      // the card/row a repeated button sits in ("Add to cart" for WHICH product)
      ctx: (() => { const c = b.closest('li,tr,article,[class*=card i],[class*=item i],[class*=row i]');
        return c && c !== document.body ? (c.innerText || '').replace(txt(b), '').replace(/\s+/g, ' ').trim().slice(0, 100) : ''; })(),
    })).filter(b => b.text).slice(0, 80),
    links, file_inputs: document.querySelectorAll('input[type=file]').length,
    password_inputs: document.querySelectorAll('input[type=password]').length,
    tables: document.querySelectorAll('table').length,
    charts: document.querySelectorAll('canvas, svg.recharts-surface, .apexcharts-canvas, [class*=chart i] svg').length,
    iframes: document.querySelectorAll('iframe').length, log_regions: logRegions,
    frameworks: {
      nextjs: !!document.querySelector('script[src*="/_next/"],link[href*="/_next/"]') || !!window.__NEXT_DATA__,
      streamlit: !!document.querySelector('[data-testid="stApp"],.stApp'),
      gradio: !!document.querySelector('gradio-app,.gradio-container'),
      react: !!document.querySelector('[data-reactroot],#root,#__next'),
    },
    text_sample: (document.body ? document.body.innerText : '').slice(0, 1500),
  };
}"""


def discover(live_url: str, known_pages: Iterable[str] = (), known_api_routes: Iterable[str] = (),
             log: Callable[[str], None] = lambda m: None, max_pages: int = MAX_PAGES,
             credentials: Optional[Dict[str, str]] = None, budget_s: int = DISCOVERY_BUDGET_S,
             cancel_event=None, session_out: Optional[Dict[str, Any]] = None,
             known_form_pages: Iterable[str] = ()) -> Dict[str, Any]:
    """credentials = {"username": ..., "password": ...} logs in first, then crawls as that user.

    session_out: when given and the login succeeded, receives {"storage_state": ...} so the executor reuses this
    session instead of logging in again (it stays in memory; never persisted).
    The crawl stops at max_pages inspected pages, MAX_NAVIGATIONS attempts, budget_s seconds or cancellation."""
    from playwright.sync_api import sync_playwright

    from engines.runtime.browser import launch_chromium, new_context
    from tools.agent_eval.net_guard import check_target

    check_target(live_url)  # raises BlockedTarget for private / internal hosts
    started = time.monotonic()
    base = urllib.parse.urlsplit(live_url)
    origin = f"{base.scheme}://{base.netloc}"
    queue: List[str] = [live_url]
    for p in known_pages:  # page routes from the code graph; parameterised ones can't be visited blind
        if p and "[" not in p and ":" not in p and "{" not in p:
            queue.append(origin + (p if p.startswith("/") else "/" + p))
    seen, pages, network = set(), [], []
    unrendered: List[str] = []
    known_form_pages = list(known_form_pages or [])
    seen_final: set = set()
    gated: List[str] = []
    login_result: Dict[str, Any] = {"attempted": False}

    stopped_by: Optional[str] = None
    with sync_playwright() as pw:
        browser = launch_chromium(pw, log)
        try:
            ctx = new_context(browser, log, accept_downloads=True)
            page = ctx.new_page()

            def on_response(resp):
                req = resp.request
                if req.resource_type in ("xhr", "fetch") and urllib.parse.urlsplit(resp.url).netloc == base.netloc:
                    network.append({"method": req.method, "path": urllib.parse.urlsplit(resp.url).path,
                                    "status": resp.status, "page": page.url})
            page.on("response", on_response)

            if credentials:
                login_result = _log_in(page, live_url, credentials, log)
                if login_result.get("succeeded"):
                    # crawl as the logged-in user from where the app landed us; the login page itself is not a target
                    landed = origin + login_result["landed_on"]
                    queue = [landed] + [u for u in queue if u.rstrip("/") != live_url.rstrip("/")]
                    seen.add(str(login_result.get("login_url") or "").split("?")[0].rstrip("/"))
                    if session_out is not None:
                        session_out["storage_state"] = ctx.storage_state()
            else:
                _goto(page, live_url, log, first=True)  # wake a cold-starting host before the timed crawl

            route_seen: set = set()
            crawl_started = time.monotonic()
            navigations = 0
            while queue and len(pages) < max_pages:
                if cancel_event is not None and cancel_event.is_set():
                    stopped_by = "cancelled"
                    break
                if navigations >= MAX_NAVIGATIONS:
                    stopped_by = f"{MAX_NAVIGATIONS} page visits"
                    break
                if time.monotonic() - crawl_started > budget_s:
                    stopped_by = f"the {budget_s // 60}-minute discovery budget"
                    break
                url = urllib.parse.urldefrag(queue.pop(0))[0].rstrip("/") or origin
                if url in seen:
                    continue
                seen.add(url)
                path = urllib.parse.urlsplit(url).path or "/"
                route = _normalise(path)
                if route != path:  # an item page such as /runs/20261001-153029: one sample shows the template
                    if route in route_seen:
                        continue
                    route_seen.add(route)
                navigations += 1
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8_000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1_000)
                    render = _wait_for_render(page)  # client-rendered apps fill in after their API calls return
                    revealed = _expand_repeaters(page)  # "+ Add" rows: their inputs only exist after a click
                    data = page.evaluate(_PAGE_SCAN_JS)
                    _tag_revealed(data, revealed)
                except Exception as exc:
                    log(f"Could not open {url}: {type(exc).__name__}")
                    continue
                data["requested_url"] = url
                data["render_wait_s"] = render.get("waited_s")
                data["status"] = resp.status if resp else None
                data["redirected_to_auth"] = bool(re.search(r"/(log-?in|sign-?in|auth)(/|$|\?)", urllib.parse.urlsplit(data["url"]).path, re.I)) \
                    and not re.search(r"/(log-?in|sign-?in|auth)", urllib.parse.urlsplit(url).path, re.I)
                if data["redirected_to_auth"]:
                    gated.append(urllib.parse.urlsplit(url).path or "/")
                final = urllib.parse.urldefrag(data["url"])[0].split("?")[0].rstrip("/")
                if final in seen_final:  # several gated pages all landing on the same login screen
                    continue
                seen_final.add(final)
                pages.append(_summarise_page(data))
                log(f"Inspected {urllib.parse.urlsplit(data['url']).path or '/'}: {len(data['forms'])} form(s), "
                    f"{len(data['buttons'])} button(s), {len(data['inputs'])} input(s)")
                # page routes the app prefetches (Next.js RSC / client navigation) are crawl hints too
                for n in network:
                    last = n["path"].rsplit("/", 1)[-1]
                    if n["method"] == "GET" and not n["path"].startswith(("/api", "/_next")) and "." not in last:
                        hint = origin + n["path"]
                        if hint.rstrip("/") not in seen and hint not in queue:
                            queue.append(hint)
                for link in data["links"]:
                    href = urllib.parse.urldefrag(link["href"])[0]
                    parts = urllib.parse.urlsplit(href)
                    if parts.netloc == base.netloc and parts.scheme in ("http", "https") and not _SKIP_LINK.search(href):
                        if href.rstrip("/") not in seen:
                            queue.append(href)
            # second look: pages the code says carry a form but that rendered no input (slow API / cold backend)
            expected = {(_normalise(urllib.parse.urlsplit(origin + (p if p.startswith("/") else "/" + p)).path) or "/")
                        for p in known_form_pages}
            for i, pg in enumerate(list(pages)):
                route = _normalise(pg.get("path") or "/")
                if route not in expected or pg.get("forms") or (cancel_event is not None and cancel_event.is_set()):
                    continue
                log(f"{pg.get('path')} rendered no form although the code defines one there; looking again "
                    f"(up to {RECHECK_WAIT_S}s for the app to finish loading).")
                try:
                    page.goto(pg.get("url") or origin + (pg.get("path") or "/"), wait_until="domcontentloaded",
                              timeout=NAV_TIMEOUT_MS)
                    _wait_for_render(page, RECHECK_WAIT_S)
                    revealed = _expand_repeaters(page)
                    data = page.evaluate(_PAGE_SCAN_JS)
                    _tag_revealed(data, revealed)
                    data.update(requested_url=pg.get("url"), status=pg.get("status"), redirected_to_auth=False,
                                render_wait_s=RECHECK_WAIT_S, rechecked=True)
                    again = _summarise_page(data)
                    if again.get("forms"):
                        pages[i] = again
                        log(f"Re-inspected {pg.get('path')}: {len(data['forms'])} form(s), {len(data['inputs'])} input(s)")
                    else:
                        unrendered.append(pg.get("path") or "/")
                except Exception as exc:
                    log(f"Could not re-open {pg.get('path')}: {type(exc).__name__}")
                    unrendered.append(pg.get("path") or "/")
        finally:
            browser.close()

    if stopped_by:
        log(f"Discovery stopped after {stopped_by}; {len(pages)} page(s) inspected.")
    prof = _profile(live_url, pages, network, list(known_api_routes), time.monotonic() - started, gated)
    prof["crawl_stopped_by"] = stopped_by
    # pages the code defines a form on that never rendered one: the app was still loading (or erroring) for MTA
    prof["unrendered_form_pages"] = unrendered
    prof["login"] = {k: v for k, v in login_result.items() if k != "storage_state"}
    if login_result.get("succeeded"):
        prof["authentication_signals"].append("logged in with the provided test account")
        prof["authentication"] = True
    prof["needs_credentials"] = bool(gated) and not login_result.get("succeeded")
    return prof


def _log_in(page, live_url: str, creds: Dict[str, str], log) -> Dict[str, Any]:
    """Find the login form, fill it, submit, and confirm the app let us in.

    Robust to the two things that break naive logins:
      * cold starts — scale-to-zero hosts (Azure Container Apps, Render, Cloud Run…) can take > 60 s to answer the first
        request, so the first navigation gets a long timeout and one retry;
      * client-rendered forms — React/Next login pages draw the form after hydration, so we WAIT for a visible password
        field (up to LOGIN_FORM_TIMEOUT_MS) instead of sleeping a fixed time.
    Where to look: the live URL, then the page's own "Log in" / "Sign in" link or button, then common login paths.
    Success = the URL leaves the login page or the password field goes away; an error message or a password field
    still showing after LOGIN_RESULT_TIMEOUT_MS = rejected.
    """
    base = urllib.parse.urlsplit(live_url)
    origin = f"{base.scheme}://{base.netloc}"
    queue: List[str] = [live_url]
    tried: List[str] = []
    paths_added = False
    while queue:
        url = queue.pop(0)
        if url.rstrip("/") in [t.rstrip("/") for t in tried]:
            continue
        tried.append(url)
        if not _goto(page, url, log, first=len(tried) == 1):
            continue
        first_page = len(tried) == 1
        # the landing page gets a short look (it is usually not the login page); login paths get the full wait
        pw = _wait_for_password(page, 8_000 if first_page and url == live_url else LOGIN_FORM_TIMEOUT_MS)
        if pw is None:
            target = _login_link(page)
            if target and target.get("href") and target["href"].rstrip("/") not in [t.rstrip("/") for t in tried]:
                queue.insert(0, target["href"])
            elif target and target.get("element") is not None:
                try:  # a "Log in" button that opens a modal or navigates client-side
                    target["element"].click(timeout=10_000)
                    pw = _wait_for_password(page, LOGIN_FORM_TIMEOUT_MS)
                except Exception:
                    pw = None
            if pw is None and not paths_added:
                queue += [origin + p for p in ("/login", "/signin", "/sign-in", "/auth/login", "/account/login", "/users/sign_in")]
                paths_added = True
            if pw is None:
                continue
        return _submit_login(page, pw, creds, page.url, log)
    shown = ", ".join(urllib.parse.urlsplit(t).path or "/" for t in tried)
    log(f"Login failed: no login form found (looked at {shown})")
    return {"attempted": True, "succeeded": False,
            "error": f"no login form found — no password field appeared within {LOGIN_FORM_TIMEOUT_MS // 1000}s on {shown}"}


def _goto(page, url: str, log, first: bool) -> bool:
    timeout = WAKE_TIMEOUT_MS if first else NAV_TIMEOUT_MS
    for attempt in range(2 if first else 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            return True
        except Exception as exc:
            log(f"Could not open {url} ({type(exc).__name__})" + (" — the app may be waking up; retrying" if first and attempt == 0 else ""))
    return False


def _wait_for_password(page, timeout_ms: int):
    try:
        page.wait_for_selector("input[type=password]", state="visible", timeout=timeout_ms)
        return page.locator("input[type=password]:visible").first
    except Exception:
        return None


def _login_link(page) -> Optional[Dict[str, Any]]:
    """The page's own way to the login form: a link (preferred, by href) or a button."""
    rx = re.compile(r"^\s*(log ?in|sign ?in|login|signin)\s*$", re.I)
    try:
        links = page.locator("a:visible").filter(has_text=rx)
        if links.count():
            href = links.first.get_attribute("href")
            if href and not href.startswith(("javascript:", "#")):
                return {"href": urllib.parse.urljoin(page.url, href)}
            return {"element": links.first}
        buttons = page.locator("button:visible, [role=button]:visible").filter(has_text=rx)
        if buttons.count():
            return {"element": buttons.first}
    except Exception:
        pass
    return None


def _submit_login(page, pw, creds: Dict[str, str], login_url: str, log) -> Dict[str, Any]:
    form = pw.locator("xpath=ancestor::form[1]")
    scope = form if form.count() else page
    user = scope.locator("input[type=email]:visible, input[autocomplete=username]:visible, input[name*=user i]:visible, "
                         "input[name*=email i]:visible, input[name*=login i]:visible, input[type=text]:visible").first
    if user.count():
        user.fill(creds.get("username", ""))
    pw.fill(creds.get("password", ""))
    button = (form.locator("button[type=submit], input[type=submit], button").first if form.count() else
              page.locator("button:visible").filter(has_text=re.compile(r"log ?in|sign ?in|continue|submit", re.I)).first)
    if button.count():
        button.click()
    else:
        pw.press("Enter")

    start_path = urllib.parse.urlsplit(login_url).path
    deadline = time.monotonic() + LOGIN_RESULT_TIMEOUT_MS / 1000
    error = None
    while time.monotonic() < deadline:
        page.wait_for_timeout(500)
        path = urllib.parse.urlsplit(page.url).path
        left = path != start_path and not re.search(r"/(log-?in|sign-?in|auth)(/|$)", path, re.I)
        pw_gone = not page.locator("input[type=password]:visible").count()
        if left or pw_gone:
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            landed = urllib.parse.urlsplit(page.url).path or "/"
            log(f"Logged in; landed on {landed}")
            return {"attempted": True, "succeeded": True, "landed_on": landed, "login_url": login_url}
        error = _visible_error(page)
        if error:
            break
    msg = error or f"still on the login page {LOGIN_RESULT_TIMEOUT_MS // 1000}s after submitting (credentials not accepted?)"
    log(f"Login failed: {msg}")
    return {"attempted": True, "succeeded": False, "error": msg, "login_url": login_url}


def _visible_error(page) -> Optional[str]:
    loc = page.locator("[role=alert]:visible, .error:visible, [class*=error i]:visible, [class*=alert i]:visible, "
                       "[aria-live]:visible")
    try:
        for i in range(min(loc.count(), 6)):
            text = (loc.nth(i).inner_text(timeout=1_000) or "").strip()
            if 2 < len(text) < 300:
                return text
    except Exception:
        pass
    return None


# ── repeater fields ("+ Add" rows) ──────────────────────────────────────────

# Buttons that add an empty input row to a list inside a form — client-side only, nothing is submitted.
_ADD_ROW_JS = r"""([mode, i, token]) => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const txt = el => ((el.innerText || el.value || '').trim() || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ');
  const isAdd = t => /^\+\s*add$|^\+$|^add (row|item|another|more|line|entry|point)$|^\+\s*add (row|item|another|more|line|entry|point)$/i.test(t);
  const labelOf = el => {
    if (el.labels && el.labels[0]) { const c = el.labels[0].cloneNode(true);
      c.querySelectorAll('input,select,textarea,option,button').forEach(n => n.remove());
      return (c.textContent || '').replace(/\s+/g, ' ').trim(); }
    const id = el.getAttribute('aria-labelledby'); if (id && document.getElementById(id)) return document.getElementById(id).innerText.trim();
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || el.id || '';
  };
  const inputs = () => [...document.querySelectorAll('input:not([type=hidden]),textarea,select,[contenteditable=true]')].filter(vis);
  const buttons = [...document.querySelectorAll('button,[role=button]')].filter(vis).filter(b => isAdd(txt(b)) && !b.disabled);
  if (mode === 'count') { inputs().forEach(el => el.setAttribute('data-aqp-known', '1')); return buttons.length; }
  if (mode === 'click') { const b = buttons[i]; if (!b) return null;
    const all = [...document.querySelectorAll('button,[role=button]')].filter(vis).filter(x => txt(x) === txt(b));
    const ctxEl = b.closest('li,tr,article,[class*=card i],[class*=item i],[class*=row i]');
    const info = { text: txt(b), nth: all.indexOf(b),
      context: ctxEl && ctxEl !== document.body ? (ctxEl.innerText || '').replace(txt(b), '').replace(/\s+/g, ' ').trim().slice(0, 100) : '' };
    b.setAttribute('data-aqp-click', token); return info; }
  // mode === 'new': inputs that appeared since the last mark
  const fresh = inputs().filter(el => !el.getAttribute('data-aqp-known'));
  fresh.forEach(el => el.setAttribute('data-aqp-known', '1'));
  return fresh.map(el => ({ label: labelOf(el).slice(0, 120), name: el.getAttribute('name') || '' }));
}"""
MAX_REPEATERS = 20


def _expand_repeaters(page) -> List[Dict[str, Any]]:
    """Click each list's "+ Add" button once so its row inputs exist, and remember which button revealed which inputs."""
    revealed: List[Dict[str, Any]] = []
    try:
        n = page.evaluate(_ADD_ROW_JS, ["count", 0, ""])
    except Exception:
        return revealed
    for i in range(min(int(n or 0), MAX_REPEATERS)):
        try:
            token = f"r{i}"
            info = page.evaluate(_ADD_ROW_JS, ["click", i, token])
            if not info:
                continue
            page.locator(f'[data-aqp-click="{token}"]').first.click(timeout=5_000)
            page.wait_for_timeout(300)
            for f in page.evaluate(_ADD_ROW_JS, ["new", 0, ""]) or []:
                revealed.append({**f, "revealed_by": info})
        except Exception:
            continue
    return revealed


def _tag_revealed(data: Dict[str, Any], revealed: List[Dict[str, Any]]) -> None:
    """Attach `revealed_by` (the "+ Add" button to click first) to the scanned fields that only exist after it."""
    if not revealed:
        return
    pool = list(revealed)
    for f in data.get("forms") or []:
        for x in f.get("fields") or []:
            hit = next((r for r in pool if r["label"] == (x.get("label") or "")[:120] and r["name"] == (x.get("name") or "")), None)
            if hit:
                x["revealed_by"] = hit["revealed_by"]
                pool.remove(hit)


# ── per-page summary ────────────────────────────────────────────────────────

def _summarise_page(d: Dict[str, Any]) -> Dict[str, Any]:
    forms = []
    for f in d["forms"]:
        fields = [x for x in f["fields"] if not x["readonly"]]
        if not fields:
            continue
        for x in fields:  # many apps mark required fields only in the label: "Name (required)", "Name *"
            if not x["required"] and _REQUIRED_LABEL.search(x.get("label") or ""):
                x["required"] = True
        submit = next((b for b in f["buttons"] if _SUBMIT_WORDS.search(b)), f["buttons"][0] if f["buttons"] else None)
        forms.append({"kind": f["kind"], "action": f["action"], "method": f["method"], "field_count": len(fields),
                      "required_fields": sum(1 for x in fields if x["required"]),
                      "fields": fields[:150], "submit_button": submit, "buttons": f["buttons"][:12],
                      "is_login": any(x["type"] == "password" for x in fields)})
    download_links = [l for l in d["links"] if l["download"] or re.search(r"\.(pdf|docx?|csv|xlsx?|zip)(\?|$)", l["href"], re.I)]
    download_buttons = [b["text"] for b in d["buttons"] if _DOWNLOAD_WORDS.search(b["text"])]
    editable_text = [x for x in d["inputs"] if x["type"] in ("textarea", "contenteditable", "text") and not x["readonly"]]
    send_buttons = [b["text"] for b in d["buttons"] if re.search(r"\b(send|ask|submit|→|➤)\b", b["text"], re.I)]
    chat_like = (d["password_inputs"] == 0                      # a login screen is never a chat
                 and 1 <= len(editable_text) <= 2                   # one message box, not a 20-field form
                 and (bool(send_buttons) or d["log_regions"] > 0)
                 and (d["log_regions"] > 0 or bool(_CHAT_WORDS.search(d["text_sample"]))
                      or bool(d["frameworks"].get("gradio")) or bool(d["frameworks"].get("streamlit"))))
    return {
        "url": d["url"], "requested_url": d["requested_url"], "path": urllib.parse.urlsplit(d["url"]).path or "/",
        "status": d["status"], "title": d["title"], "headings": d["headings"][:12],
        "forms": forms, "buttons": [b["text"] for b in d["buttons"]][:40],
        "button_context": [b.get("ctx") or "" for b in d["buttons"]][:40],
        "links": sorted({urllib.parse.urlsplit(l["href"]).path for l in d["links"]
                         if urllib.parse.urlsplit(l["href"]).netloc == urllib.parse.urlsplit(d["url"]).netloc})[:40],
        "downloads": {"links": [l["href"] for l in download_links][:10], "buttons": download_buttons[:10]},
        "file_uploads": d["file_inputs"], "chat_interface": chat_like,
        "auth": {"password_fields": d["password_inputs"], "login_words": bool(_AUTH_WORDS.search(d["text_sample"][:600])),
                 "redirected_to_login": d["redirected_to_auth"]},
        "tables": d["tables"], "charts": d["charts"], "iframes": d["iframes"], "frameworks": d["frameworks"],
    }


# ── whole-app profile ───────────────────────────────────────────────────────

def _profile(live_url: str, pages: List[Dict], network: List[Dict], api_routes: List[str], seconds: float,
             gated: Optional[List[str]] = None) -> Dict[str, Any]:
    gated = sorted(set(gated or []))
    forms = [dict(f, page=p["path"]) for p in pages for f in p["forms"]]
    app_forms = [f for f in forms if not f["is_login"]]
    buttons = sorted({b for p in pages for b in p["buttons"]})
    downloads = any(p["downloads"]["links"] or p["downloads"]["buttons"] for p in pages)
    chat = any(p["chat_interface"] for p in pages)
    api_calls = sorted({(n["method"], _normalise(n["path"]), n["status"]) for n in network})
    api_denied = [c for c in api_calls if c[2] in (401, 403)]
    login_form = any(f["is_login"] for f in forms)
    redirected = any(p["auth"]["redirected_to_login"] for p in pages)
    gate_note = f"{len(gated)} page(s) redirect to login: {', '.join(gated[:6])}" if gated else "redirect to login"
    auth_signals = [s for s, on in (("login form", login_form), (gate_note, redirected or bool(gated)),
                                    (f"{len(api_denied)} API call(s) answered 401/403", bool(api_denied))) if on]
    frameworks = sorted({k for p in pages for k, v in p["frameworks"].items() if v})
    # code-known API routes the frontend should be calling (e.g. document generation) — kept for later engines
    generation_routes = [r for r in api_routes if re.search(r"generat|export|download|report|render|create", r, re.I)]

    app_type, reasons = _classify(pages, app_forms, downloads, chat, generation_routes, frameworks)
    if gated and not app_forms and not chat:
        # only the login/register screens were visible: the real app is hidden, so do not guess its type
        app_type = "Behind login"
        reasons = [f"{len(gated)} page(s) redirect to the login screen; provide a test account so MTA can see the app"]
    flows = _flows(pages, app_forms, downloads, generation_routes)
    return {
        "app_type": app_type,
        "forms": len(app_forms),
        "buttons": len(buttons),
        "downloads": downloads,
        "chat_interface": chat,
        "authentication": bool(auth_signals),
        # ── details ──
        "live_url": live_url,
        "pages_inspected": len(pages),
        "gated_pages": gated,
        "classification_signals": reasons,
        "authentication_signals": auth_signals,
        "file_uploads": sum(p["file_uploads"] for p in pages),
        "frameworks": frameworks,
        "api_calls": [{"method": m, "path": pth, "status": st} for m, pth, st in api_calls][:60],
        "user_flows": flows,
        "pages": pages,
        "duration_s": round(seconds, 1),
    }


_ID_SEGMENT = re.compile(r"^(?=.*\d)[0-9a-f-]{8,}$|^\d{3,}$|^[A-Za-z0-9_-]{20,}$|^(?=(?:.*\d){6})[A-Za-z0-9_.-]{6,}$", re.I)


def _normalise(path: str) -> str:
    """A route template: path segments that look like record ids (numbers, hex/uuid, dated or long tokens) → {id}."""
    return "/".join("{id}" if seg and _ID_SEGMENT.match(seg) else seg for seg in (path or "/").split("/")) or "/"


def _classify(pages, forms, downloads, chat, generation_routes, frameworks):
    """Preliminary app type from DOM signals (the App Classification Engine refines it)."""
    reasons: List[str] = []
    rich_forms = [f for f in forms if f["field_count"] >= 3]
    charts = sum(p["charts"] for p in pages)
    tables = sum(p["tables"] for p in pages)
    kinds = []
    if chat:
        kinds.append("Chatbot"); reasons.append("editable message box with a send control / chat log region")
    if rich_forms and (downloads or generation_routes):
        kinds.append("Document Generator")
        reasons.append(f"{len(rich_forms)} multi-field form(s) + "
                       + ("download/export controls" if downloads else f"generation route(s) {', '.join(generation_routes[:3])}"))
    elif forms:
        kinds.append("Form Application"); reasons.append(f"{len(forms)} form(s) collecting user input")
    if charts >= 2 or tables >= 3:
        kinds.append("Dashboard"); reasons.append(f"{charts} chart(s), {tables} table(s)")
    if not pages:
        return "Unreachable", ["no page could be opened"]
    if not kinds:
        if any(p["buttons"] for p in pages) or sum(len(p["links"]) for p in pages) > 3:
            return "Static Website", ["content and navigation only; no inputs, forms or chat"]
        return "Unknown", ["no interactive elements found"]
    if len(kinds) > 1:
        return "Hybrid Application", reasons + [f"combines {', '.join(kinds)}"]
    return kinds[0], reasons


def _flows(pages, forms, downloads, generation_routes) -> List[Dict[str, Any]]:
    flows = []
    for f in forms:
        steps = [f"Open {f['page']}", f"Fill {f['field_count']} field(s)"
                 + (f" ({f['required_fields']} required)" if f["required_fields"] else "")]
        if f["submit_button"]:
            steps.append(f"Click '{f['submit_button']}'")
        outcome = "download / export" if downloads else ("generated output" if generation_routes else "result or confirmation")
        steps.append(f"Expect {outcome}")
        flows.append({"name": f"Submit form on {f['page']}", "entry": f["page"], "steps": steps,
                      "form_fields": [x["label"] or x["name"] for x in f["fields"]][:20]})
    for p in pages:
        if p["chat_interface"]:
            flows.append({"name": f"Converse on {p['path']}", "entry": p["path"],
                          "steps": [f"Open {p['path']}", "Type a message", "Send", "Read the reply"]})
    login = next((dict(f, page=p["path"]) for p in pages for f in p["forms"] if f["is_login"]), None)
    if login:
        flows.insert(0, {"name": "Log in", "entry": login["page"],
                         "steps": [f"Open {login['page']}", "Enter credentials", f"Click '{login['submit_button'] or 'Log in'}'",
                                   "Expect an authenticated page"]})
    return flows[:20]
