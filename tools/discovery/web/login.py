"""login.py — find a login form, fill it, submit, confirm (moved from engines/runtime/discovery.py, unchanged)."""

import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

NAV_TIMEOUT_MS = 45_000
WAKE_TIMEOUT_MS = 120_000          # first request to a scale-to-zero host can take over a minute
LOGIN_FORM_TIMEOUT_MS = 25_000     # client-rendered login forms appear after hydration
LOGIN_RESULT_TIMEOUT_MS = 25_000


def log_in(page, live_url: str, creds: Dict[str, str], log) -> Dict[str, Any]:
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
        if not goto(page, url, log, first=len(tried) == 1):
            continue
        first_page = len(tried) == 1
        # the landing page gets a short look (it is usually not the login page); login paths get the full wait
        pw = wait_for_password(page, 8_000 if first_page and url == live_url else LOGIN_FORM_TIMEOUT_MS)
        if pw is None:
            target = login_link(page)
            if target and target.get("href") and target["href"].rstrip("/") not in [t.rstrip("/") for t in tried]:
                queue.insert(0, target["href"])
            elif target and target.get("element") is not None:
                try:  # a "Log in" button that opens a modal or navigates client-side
                    target["element"].click(timeout=10_000)
                    pw = wait_for_password(page, LOGIN_FORM_TIMEOUT_MS)
                except Exception:
                    pw = None
            if pw is None and not paths_added:
                queue += [origin + p for p in ("/login", "/signin", "/sign-in", "/auth/login", "/account/login", "/users/sign_in")]
                paths_added = True
            if pw is None:
                continue
        return submit_login(page, pw, creds, page.url, log)
    shown = ", ".join(urllib.parse.urlsplit(t).path or "/" for t in tried)
    log(f"Login failed: no login form found (looked at {shown})")
    return {"attempted": True, "succeeded": False,
            "error": f"no login form found — no password field appeared within {LOGIN_FORM_TIMEOUT_MS // 1000}s on {shown}"}


def goto(page, url: str, log, first: bool) -> bool:
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


def wait_for_password(page, timeout_ms: int):
    try:
        page.wait_for_selector("input[type=password]", state="visible", timeout=timeout_ms)
        return page.locator("input[type=password]:visible").first
    except Exception:
        return None


def login_link(page) -> Optional[Dict[str, Any]]:
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


def submit_login(page, pw, creds: Dict[str, str], login_url: str, log) -> Dict[str, Any]:
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
        error = visible_error(page)
        if error:
            break
    msg = error or f"still on the login page {LOGIN_RESULT_TIMEOUT_MS // 1000}s after submitting (credentials not accepted?)"
    log(f"Login failed: {msg}")
    return {"attempted": True, "succeeded": False, "error": msg, "login_url": login_url}


def visible_error(page) -> Optional[str]:
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
