"""
executor.py — Playwright Executor.

    run = execute_plans(live_url, action_plan, artifact_dir, credentials=..., log=...)

Runs every ready plan from the Action Generation Engine in a real Chromium browser and records exactly
what happened. It decides nothing about pass/fail; that is the Output Validation and Pass/Fail engines'
job. Per plan it keeps:
  * per-step outcome (passed / failed / skipped / deferred), duration, the locator strategy that worked, errors;
  * captures written to `artifact_dir/<plan_id>/`: full-page screenshot (plus one at the failing step),
    visible page text, the chat reply (text that appeared after sending), downloaded files (name, size, sha256),
    HTTP response bodies;
  * observations: same-origin XHR/fetch calls with status and duration, console errors, uncaught page errors;
  * the judged expectations, handed on unevaluated to Output Validation.

Execution model:
  * One session for the whole run: the session Runtime Discovery logged in with is reused (storage state handed on
    in memory); only without it does the executor log in itself (one retry). Each plan starts logged in, in a
    fresh, isolated context; a plan redirected to the login page re-logs in once.
  * Adaptive parallelism: up to `workers` browsers. With `calibrate` (document generators — heavy server-side work),
    the first generating plan runs alone to measure the app's generation time; plans then run in parallel, and the
    executor drops back to one at a time as soon as a parallel plan's generation is SLOWDOWN_FACTOR× slower than
    that baseline (or the app stays busy past its wait limit), so parallelism never distorts results. Plans about
    timing / latency always run alone.
  * A per-plan time limit (enforced inside long waits too), an overall budget (plans not started in time are
    `not_run`, never silently dropped) and cancellation between steps.
  * Navigation and HTTP steps never leave the live app's origin; every browser context carries the SSRF guard.
  * Targets are resolved in-page with the same label/name/context rules Runtime Discovery used to describe
    them, so a plan's target resolves to the element discovery saw. Playwright's label/placeholder/role
    locators are the fallback.
  * After a failing step the remaining actions are skipped, but captures still run: a failed run still
    leaves evidence.
Credentials are used only for the login and are never written to results, logs or artifacts.
"""

import hashlib
import queue
import re
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from engines.runtime.discovery import NAV_TIMEOUT_MS, _log_in
from tools.agent_eval.net_guard import join_same_origin

WORKERS = 3
DOC_GENERATOR_WORKERS = 2
SLOWDOWN_FACTOR = 1.8
PLAN_TIMEOUT_S = 900   # a revise test generates twice; document generators take minutes
BUDGET_S = 3600
SERIAL_BUDGET_S = 5400  # one plan at a time (heavy server-side generation) needs a longer overall budget
LOCATE_TIMEOUT_MS = 20_000
DOWNLOAD_LOCATE_TIMEOUT_MS = 30_000
DOWNLOAD_TIMEOUT_MS = 90_000
CLICK_TIMEOUT_MS = 15_000
DOM_TEXT_LIMIT = 50_000
EXCERPT = 1500
_LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|auth)(/|$|\?)", re.I)
_TIMING = re.compile(r"\b(latency|response time|performance|completes? (with)?in|(under|within|less than) \d+\s*"
                     r"(s|sec|secs|seconds|minutes?))\b", re.I)

# Mirrors the target description Runtime Discovery produced (labelOf / txt / ctx in discovery._PAGE_SCAN_JS).
# Marks the best-matching visible element with a one-off attribute and returns it, or null.
_RESOLVE_JS = r"""([t, token]) => {
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
  const ctxOf = b => { const c = b.closest('li,tr,article,[class*=card i],[class*=item i],[class*=row i]');
    return c && c !== document.body ? (c.innerText || '').replace(txt(b), '').replace(/\s+/g, ' ').trim().slice(0, 100) : ''; };
  let pick = null;
  if (t.kind === 'field') {
    const els = [...document.querySelectorAll('input:not([type=hidden]),textarea,select,[contenteditable=true],[role=textbox]')].filter(vis);
    const lab = (t.label || '').slice(0, 120);
    pick = els.find(e => t.name && e.getAttribute('name') === t.name && labelOf(e).slice(0, 120) === lab)
        || els.find(e => lab && labelOf(e).slice(0, 120) === lab)
        || els.find(e => t.name && e.getAttribute('name') === t.name);
  } else if (t.kind === 'button') {
    const els = [...document.querySelectorAll('button,[role=button],input[type=submit],input[type=button]')].filter(vis)
      .filter(b => txt(b) === t.text);
    if (t.context) pick = els.find(b => ctxOf(b) === t.context) || els.find(b => ctxOf(b).startsWith(t.context.slice(0, 40)));
    if (!pick && Number.isInteger(t.nth)) pick = els[t.nth];
    if (!pick) pick = els[0];
  } else if (t.kind === 'link' && t.href) {
    const path = new URL(t.href, location.href).pathname;
    pick = [...document.querySelectorAll('a[href]')].filter(vis).find(a => a.href === t.href)
        || [...document.querySelectorAll('a[href]')].filter(vis).find(a => new URL(a.href).pathname === path);
  }
  if (!pick) return false;
  pick.setAttribute('data-aqp-target', token);
  return true;
}"""

_BUSY_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const text = (document.body && document.body.innerText) || '';
  const indicator = [...document.querySelectorAll('[aria-busy=true],[role=progressbar],[class*=spinner i],[class*=loading i],[class*=skeleton i]')]
    .some(vis);
  // apps that only SAY they are working ("Generating your documents — this usually takes 30-90 seconds…"):
  // only short status-like lines count, so generated content that merely mentions "processing" does not
  const status = /^(\W{0,3})(generating|processing|analy[sz]ing|uploading|loading|working|creating|preparing|thinking)\b.{0,120}(\.\.\.|…|please|wait|take)|please wait|this (usually|may|can) take|hang tight|in progress\W*$/i;
  const wording = text.split('\n').some(l => { const t = l.trim(); return t.length > 0 && t.length < 200 && status.test(t); });
  return [indicator || wording, text.length];
}"""

_FIXTURES = {
    ".txt": b"MTA automated acceptance test fixture.\nThis file was uploaded by the Playwright Executor.\n",
    ".csv": b"name,value\nalpha,1\nbeta,2\n",
    ".json": b'{"fixture": "aqp", "items": [1, 2, 3]}\n',
    ".pdf": (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
             b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"),
    ".png": bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                          "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"),
}


class StepFailed(Exception):
    pass


class _Slots:
    """Adaptive concurrency gate shared by the worker threads (see the module docstring)."""

    def __init__(self, workers: int, calibrate: bool, say: Callable[..., None]) -> None:
        self.max = max(1, workers)
        self.allowed = 1 if calibrate and self.max > 1 else self.max
        self.calibrating = calibrate and self.max > 1
        self.baseline: Optional[float] = None
        self.active = 0
        self.exclusive = False
        self.cond = threading.Condition()
        self.say = say

    def acquire(self, exclusive: bool) -> int:
        with self.cond:
            while self.exclusive or (exclusive and self.active) or (not exclusive and self.active >= self.allowed):
                self.cond.wait(1.0)
            self.active += 1
            self.exclusive = exclusive
            return self.active

    def release(self, res: Dict[str, Any], ran_with: int) -> None:
        gen = _generation_seconds(res)
        with self.cond:
            self.active -= 1
            self.exclusive = False
            if self.calibrating and gen:
                self.baseline, self.calibrating, self.allowed = gen, False, self.max
                self.say(f"The app generates a result in about {gen:.0f}s; running up to {self.max} tests in parallel "
                         "(back to one at a time if that slows the app down).")
            elif self.allowed > 1 and ran_with > 1 and (
                    (self.baseline and gen and gen > SLOWDOWN_FACTOR * self.baseline)
                    or "still busy after" in str(res.get("error") or "")):
                self.allowed = 1
                self.say(f"The app slowed down under parallel tests ({gen or 0:.0f}s vs {self.baseline or 0:.0f}s alone); "
                         "running the remaining tests one at a time.", "warning")
            self.cond.notify_all()


def _generation_seconds(res: Dict[str, Any]) -> Optional[float]:
    waits = [s.get("duration_ms", 0) for s in res.get("steps") or [] if s.get("action") == "wait_for"]
    return sum(waits) / 1000 if waits and res.get("status") == "completed" else None


def _timing_sensitive(plan: Dict[str, Any]) -> bool:
    text = " ".join([plan.get("title") or ""] + [str(s.get("expectation") or "") for s in plan.get("steps") or []
                                                 if s.get("action") == "assert"])
    return bool(_TIMING.search(text))


def execute_plans(live_url: str, action_plan: Optional[Dict[str, Any]], artifact_dir: Path,
                  credentials: Optional[Dict[str, str]] = None, log: Callable[..., None] = lambda *a, **k: None,
                  on_result: Optional[Callable[[Dict[str, Any]], None]] = None, workers: int = WORKERS,
                  on_progress: Optional[Callable[[str], None]] = None,
                  plan_timeout_s: int = PLAN_TIMEOUT_S, budget_s: int = BUDGET_S,
                  storage_state: Optional[Dict[str, Any]] = None, calibrate: bool = False,
                  cancel_event=None) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    from engines.runtime.browser import launch_chromium, new_context
    from tools.agent_eval.net_guard import check_target

    started = time.monotonic()
    plans = [p for p in (action_plan or {}).get("plans") or [] if p.get("status") == "ready" and p.get("steps")]
    # BRD tests first, timing-sensitive ones last (they run alone), unscored flow checks at the very end
    plans.sort(key=lambda p: (not p.get("scored", True), _timing_sensitive(p)))
    if not plans:
        return _summary("skipped", [], started, reason=(action_plan or {}).get("reason") or "no executable plans")
    check_target(live_url)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def say(msg: str, level: str = "info") -> None:
        with lock:
            log(msg, level)

    needs_login = any(s["action"] == "login" for p in plans for s in p["steps"])
    login: Dict[str, Any] = {"attempted": False}
    if needs_login and storage_state:
        login = {"attempted": True, "succeeded": True, "reused": True}
        say(f"Reusing the session Runtime Discovery logged in with for {len(plans)} plan(s).")
    elif needs_login:
        if not credentials:
            results = [_blocked(p, "the plan needs a login but no test account is configured") for p in plans]
            return _summary("blocked", results, started, reason="No test account configured for a logged-in app.")
        with sync_playwright() as pw:
            browser = launch_chromium(pw, say)
            try:
                for attempt in range(2):  # cold-starting hosts and flaky login pages get one more chance
                    ctx = new_context(browser, say)
                    login = _log_in(ctx.new_page(), live_url, credentials, lambda m: None)
                    if login.get("succeeded"):
                        storage_state = ctx.storage_state()
                        ctx.close()
                        break
                    ctx.close()
                    if attempt == 0:
                        say(f"Login with the test account failed ({login.get('error')}); retrying once.", "warning")
                        time.sleep(10)
            finally:
                browser.close()
        login = {k: v for k, v in login.items() if k in ("attempted", "succeeded", "error", "landed_on")}
        if not login.get("succeeded"):
            results = [_blocked(p, f"login with the test account failed: {login.get('error')}") for p in plans]
            say(f"Login with the test account failed twice ({login.get('error')}); no plan was run.", "warning")
            return _summary("blocked", results, started, reason="Login with the test account failed.", login=login)
        say(f"Logged in once with the test account; sharing the session with {len(plans)} plan(s).")

    fixtures = artifact_dir / "_fixtures"
    fixtures.mkdir(exist_ok=True)
    for ext, data in _FIXTURES.items():
        (fixtures / f"aqp-fixture{ext}").write_bytes(data)

    todo: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    for p in plans:
        todo.put(p)
    results: Dict[str, Dict[str, Any]] = {}
    deadline = started + budget_s
    total = len(plans)
    started_count = [0]
    exec_started = time.monotonic()
    n_threads = max(1, min(workers, total))
    slots = _Slots(n_threads, calibrate, say)

    def progress() -> None:
        if not on_progress:
            return
        done = len(results)
        if done == 0:
            on_progress(f"0/{total} tests done")
            return
        par = max(1, slots.allowed)
        per = (time.monotonic() - exec_started) / done  # observed wall-clock per finished test (parallelism included)
        left = max(0, total - done) * per
        mins = max(1, round(left / 60)) if left else 0
        on_progress(f"{done}/{total} tests done" + (f" · about {mins} min left" if left else "")
                    + (f" · {par} in parallel" if par > 1 else ""))

    def finish(plan: Dict[str, Any], res: Dict[str, Any]) -> None:
        with lock:
            results[plan["plan_id"]] = res
            log(_one_line(res), "success" if res["status"] == "completed" else "warning")
            if on_result:
                on_result(res)
            progress()

    def worker() -> None:
        with sync_playwright() as pw:
            browser = launch_chromium(pw, say)
            try:
                while True:
                    try:
                        plan = todo.get_nowait()
                    except queue.Empty:
                        return
                    if cancel_event is not None and cancel_event.is_set():
                        finish(plan, _blocked(plan, "the run was cancelled before this test started", status="not_run"))
                        continue
                    if time.monotonic() > deadline:
                        finish(plan, _blocked(plan, "the execution time budget ran out before this plan started",
                                              status="not_run"))
                        continue
                    exclusive = _timing_sensitive(plan)
                    ran_with = slots.acquire(exclusive)
                    res: Dict[str, Any] = {}
                    try:
                        with lock:
                            started_count[0] += 1
                            k = started_count[0]
                        say(f"Test {k}/{total}: {plan.get('test_code') or plan['plan_id']} — {(plan.get('title') or '')[:120]}"
                            + (" (alone: timing-sensitive)" if exclusive and n_threads > 1 else ""))
                        remaining = max(60, int(deadline - time.monotonic()))
                        res = _run_plan(browser, live_url, plan, artifact_dir / _safe(plan["plan_id"]), fixtures,
                                        storage_state, credentials, min(plan_timeout_s, remaining), cancel_event, say)
                        ran_with = max(ran_with, slots.active)
                    except Exception as exc:  # never lose a plan: an MTA-side crash is recorded as such
                        res = _blocked(plan, f"MTA's browser run crashed: {_short(exc)}", status="error")
                    finally:
                        slots.release(res, ran_with)
                    finish(plan, res)
            finally:
                browser.close()

    progress()
    threads = [threading.Thread(target=worker, daemon=True, name=f"aqp-exec-{i}") for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ordered = [results[p["plan_id"]] for p in plans if p["plan_id"] in results]
    failed = sum(1 for r in ordered if r["status"] != "completed")
    out = _summary("completed" if not failed else "partial", ordered, started, login=login)
    out["parallelism"] = {"max": n_threads, "final": slots.allowed, "baseline_generation_s": slots.baseline}
    return out


# ── one plan ────────────────────────────────────────────────────────────────

def _run_plan(browser, live_url: str, plan: Dict[str, Any], out: Path, fixtures: Path,
              storage_state: Optional[Dict], credentials: Optional[Dict[str, str]], timeout_s: int,
              cancel_event=None, log: Callable[..., None] = lambda *a, **k: None) -> Dict[str, Any]:
    from engines.runtime.browser import new_context

    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    host = urllib.parse.urlsplit(live_url).netloc
    obs: Dict[str, Any] = {"network": [], "console_errors": [], "page_errors": []}
    inflight: Dict[Any, float] = {}
    state: Dict[str, Any] = {"downloads": [], "reply": None, "baseline": None, "response": None,
                             "deadline": t0 + timeout_s}
    res: Dict[str, Any] = {k: plan.get(k) for k in ("plan_id", "test_id", "test_code", "criterion_code", "requirement_ref",
                                                     "title", "class", "kind", "scored", "variant")}
    steps_out: List[Dict[str, Any]] = []
    failed: Optional[Dict[str, Any]] = None
    ctx = new_context(browser, log, accept_downloads=True, storage_state=storage_state)
    try:
        page = ctx.new_page()
        page.set_default_timeout(CLICK_TIMEOUT_MS)

        def same_origin(req) -> bool:
            return req.resource_type in ("xhr", "fetch") and urllib.parse.urlsplit(req.url).netloc == host

        page.on("request", lambda r: inflight.__setitem__(r, time.monotonic()) if same_origin(r) else None)

        def done(r, failed_req=False):
            began = inflight.pop(r, None)
            if began is not None and len(obs["network"]) < 200:
                resp = None if failed_req else r.response()
                obs["network"].append({"method": r.method, "path": urllib.parse.urlsplit(r.url).path,
                                       "status": resp.status if resp else 0, "ms": int((time.monotonic() - began) * 1000)})
        page.on("requestfinished", lambda r: done(r))
        page.on("requestfailed", lambda r: done(r, True))
        page.on("console", lambda m: obs["console_errors"].append(m.text[:300])
                if m.type == "error" and len(obs["console_errors"]) < 30 else None)
        page.on("pageerror", lambda e: obs["page_errors"].append(str(e)[:300]) if len(obs["page_errors"]) < 30 else None)

        for step in plan["steps"]:
            a = step["action"]
            rec = {"n": step["n"], "action": a, "status": "passed", "duration_ms": 0}
            s0 = time.monotonic()
            if a == "capture":
                rec.update(_capture(page, ctx, live_url, step, out, state))
            elif a == "assert":
                if step.get("kind") == "judge":
                    rec["status"] = "deferred"  # judged later by Output Validation
                elif failed:
                    rec["status"] = "skipped"
                else:
                    rec.update(_structural_assert(page, step))
            elif failed:
                rec["status"] = "skipped"
            elif cancel_event is not None and cancel_event.is_set():
                rec.update(status="failed", error="cancelled by the user")
                failed = rec
            elif time.monotonic() - t0 > timeout_s:
                rec.update(status="failed", error=f"plan time limit ({timeout_s}s) reached")
                failed = rec
            else:
                try:
                    rec.update(_do(page, ctx, live_url, step, out, fixtures, state, inflight, storage_state, credentials) or {})
                except Exception as exc:  # StepFailed or a Playwright error
                    if step.get("optional"):  # e.g. a demo-data prefill the page no longer offers
                        rec.update(status="skipped", detail=f"optional step skipped: {_short(exc)}")
                        rec["duration_ms"] = int((time.monotonic() - s0) * 1000)
                        steps_out.append(rec)
                        continue
                    rec.update(status="failed", error=_short(exc))
                    failed = rec
                    try:
                        page.screenshot(path=str(out / f"failure-step{step['n']}.png"), full_page=True)
                        rec["screenshot"] = f"{out.name}/failure-step{step['n']}.png"
                    except Exception:
                        pass
            rec["duration_ms"] = int((time.monotonic() - s0) * 1000)
            steps_out.append(rec)
        res["final_url"] = urllib.parse.urlsplit(page.url).path or "/"
    except Exception as exc:
        failed = failed or {"n": None, "error": _short(exc)}
        res["error"] = _short(exc)
    finally:
        try:
            ctx.close()
        except Exception:
            pass

    cancelled = bool(failed and failed.get("error") == "cancelled by the user")
    res.update(
        status="completed" if not failed else "not_run" if cancelled else ("error" if failed.get("n") is None else "failed"),
        failed_step=failed.get("n") if failed else None,
        error=(failed or {}).get("error") or res.get("error"),
        duration_ms=int((time.monotonic() - t0) * 1000),
        steps=steps_out,
        captures={"screenshot": state.get("screenshot"), "dom_text": state.get("dom_text"), "dom_before": state.get("dom_before"),
                  "views": state.get("views") or [],
                  "dom_excerpt": state.get("dom_excerpt"), "reply": state.get("reply"),
                  "downloads": state["downloads"], "response": state.get("response")},
        observations={**obs, "http_errors": sum(1 for n in obs["network"] if n["status"] >= 400 or n["status"] == 0)},
        expectations=[{"expectation": s.get("expectation"), "pass_criteria": s.get("pass_criteria") or []}
                      for s in plan["steps"] if s["action"] == "assert" and s.get("kind") == "judge"],
    )
    return res


def _do(page, ctx, live_url, step, out: Path, fixtures: Path, state, inflight, storage_state, credentials) -> Dict[str, Any]:
    a = step["action"]
    if a == "login":
        if storage_state:
            return {"detail": "session restored from the shared login"}
        login = _log_in(page, live_url, credentials or {}, lambda m: None)
        if not login.get("succeeded"):
            raise StepFailed(f"login failed: {login.get('error')}")
        return {"detail": f"logged in, landed on {login.get('landed_on')}"}
    if a == "goto":
        url = join_same_origin(live_url, step["url"])
        if not url:
            raise StepFailed(f"refused to leave the live app's origin ({str(step['url'])[:80]})")
        resp = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        _quiet_networkidle(page, 8_000)
        page.wait_for_timeout(1_000)
        landed = urllib.parse.urlsplit(page.url).path
        if _LOGIN_PATH.search(landed) and not _LOGIN_PATH.search(step["url"]):
            if not credentials:
                raise StepFailed(f"redirected to the login page ({landed})")
            if not _log_in(page, live_url, credentials, lambda m: None).get("succeeded"):
                raise StepFailed("session expired and re-login failed")
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            _quiet_networkidle(page, 8_000)
        status = resp.status if resp else None
        state.setdefault("page_before", _body_text(page))  # what the page showed before any action (Evidence diff)
        if status and status >= 400:
            # single-page apps often answer 404 for deep links yet render the page client-side: judge by what rendered
            text = _body_text(page)
            if status >= 500 or len(text.strip()) < 200 or re.search(r"\b(404|not found|page not found|error)\b",
                                                                    f"{page.title()} {text[:300]}", re.I):
                raise StepFailed(f"HTTP {status} opening {step['url']}")
        return {"detail": f"opened {urllib.parse.urlsplit(page.url).path or '/'}"
                + (f" (HTTP {status}, page rendered client-side)" if status and status >= 400 else f" (HTTP {status})" if status else "")}
    if a == "http":
        return _http(ctx, live_url, step, out, state)
    if a == "follow_up":
        return _follow_up(page, step)
    if a == "wait_for":
        return _settle(page, _bounded(step.get("timeout_ms") or 30_000, state), inflight, state)

    if a == "expect_download" and step["target"].get("kind") == "auto":
        return _auto_downloads(page, out, state)
    loc, how = _locate(page, step["target"], DOWNLOAD_LOCATE_TIMEOUT_MS if a == "expect_download" else LOCATE_TIMEOUT_MS)
    if a == "fill":
        loc.fill(step.get("value") or "")
        return {"locator": how}
    if a == "select":
        try:
            loc.select_option(label=step["value"])
        except Exception:
            try:
                loc.select_option(value=step["value"])
            except Exception:  # custom (non-native) dropdown
                loc.click()
                page.get_by_role("option", name=step["value"], exact=True).first.click()
        return {"locator": how}
    if a == "check":
        try:
            loc.check()
        except Exception:
            loc.click()
        return {"locator": how}
    if a == "upload":
        accept = (loc.get_attribute("accept") or "").lower()
        want = (step.get("value") or "").lower()
        ext = next((e for e in (".pdf", ".csv", ".json", ".png", ".txt") if e in accept or e[1:] in want), ".txt")
        loc.set_input_files(str(fixtures / f"aqp-fixture{ext}"))
        return {"locator": how, "detail": f"uploaded aqp-fixture{ext}"}
    if a == "click":
        loc.click(timeout=CLICK_TIMEOUT_MS)
        _quiet_networkidle(page, 3_000)
        return {"locator": how}
    if a == "send_message":
        state["baseline"] = _body_text(page)
        loc.fill(step.get("value") or "")
        send = page.locator("button:visible, [role=button]:visible, input[type=submit]:visible").filter(
            has_text=re.compile(r"^\s*(send|ask|submit|→|➤)\s*$", re.I))
        if send.count():
            send.first.click()
        else:
            loc.press("Enter")
        return {"locator": how}
    if a == "expect_download":
        with page.expect_download(timeout=_bounded(DOWNLOAD_TIMEOUT_MS, state)) as info:
            loc.click()
        meta = _save_download(info.value, out, state)
        return {"locator": how, "detail": f"downloaded {meta['name']} ({meta['size']} bytes, {meta['kind']})"}
    raise StepFailed(f"unknown action {a}")


def _bounded(timeout_ms: int, state: Dict[str, Any]) -> int:
    """A wait never runs past the plan's own time limit (at least 5 s, so the step can still report)."""
    left_ms = int((state.get("deadline", time.monotonic() + 3600) - time.monotonic()) * 1000)
    return max(5_000, min(int(timeout_ms), left_ms))


def _save_download(d, out: Path, state) -> Dict[str, Any]:
    if d.failure():
        raise StepFailed(f"download failed: {d.failure()}")
    dl_dir = out / "downloads"
    dl_dir.mkdir(exist_ok=True)
    name = _safe(d.suggested_filename or "download.bin")
    if any(m["file"].endswith(f"/{name}") for m in state["downloads"]):
        name = f"{len(state['downloads'])}-{name}"
    path = dl_dir / name
    d.save_as(str(path))
    data = path.read_bytes()
    meta = {"file": f"{out.name}/downloads/{name}", "name": d.suggested_filename, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "kind": _sniff(data, name)}
    state["downloads"].append(meta)
    if not data:
        raise StepFailed("the downloaded file is empty")
    return meta


_CONTROL_SELECTOR = "a[download], a, button, [role=button], [role=menuitem]"
_CONTROLS_JS = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  return [...document.querySelectorAll("a[download], a, button, [role=button], [role=menuitem]")]
    .map((el, i) => [i, (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 80), el.hasAttribute('download'),
                     !el.disabled && el.getAttribute('aria-disabled') !== 'true', vis(el)])
    .filter(r => r[4]).slice(0, 300).map(r => r.slice(0, 4));
}"""
_DOWNLOAD_TEXT = re.compile(r"\b(download|export|save as|docx|pdf|word|\.csv|\.xlsx)\b", re.I)


_TAB_SELECTOR = ("[role=tab]:visible, [data-tab]:visible, button[class*='tab-' i]:visible, "
                 "button[class*='-tab' i]:visible, button[class*='tab_' i]:visible")
_PRINT = re.compile(r"\bprint\b", re.I)


def _auto_downloads(page, out: Path, state) -> Dict[str, Any]:
    """Collect what the generated result offers. If the result is split into tabs (BRD / TSD / Diagram …), open each tab,
    keep its text and a screenshot as a 'view', and use that tab's download/export control; otherwise click up to 4
    download/export controls (incl. menu items) on the page. Print buttons are skipped (they open print dialogs)."""
    tabs = _result_tabs(page)
    if not tabs:
        tried = _download_here(page, out, state, wait_for_control=True, limit=4)
    else:
        tried, views = [], []
        for i, (el, label) in enumerate(tabs):
            try:
                el.click(timeout=CLICK_TIMEOUT_MS)
                page.wait_for_timeout(1_500)
            except Exception:
                continue
            name = _safe(label)[:40]
            text = _body_text(page)[:DOM_TEXT_LIMIT]
            (out / f"view-{name}.txt").write_text(text, encoding="utf-8")
            shot = None
            try:
                page.screenshot(path=str(out / f"view-{name}.png"), full_page=True)
                shot = f"{out.name}/view-{name}.png"
            except Exception:
                pass
            views.append({"name": label, "text_file": f"{out.name}/view-{name}.txt", "screenshot": shot})
            tried += _download_here(page, out, state, wait_for_control=i == 0, limit=2)
        state["views"] = views
        if views and not state["downloads"]:
            return {"locator": "auto", "detail": f"opened {len(views)} result view(s): {', '.join(v['name'] for v in views)}; "
                                                 "no downloadable file was offered"}
    if not state["downloads"]:
        raise StepFailed("no download was produced" + (f" (tried: {', '.join(tried)})" if tried
                                                        else ": no download or export control appeared"))
    names = ", ".join(m["name"] for m in state["downloads"])
    views = state.get("views") or []
    return {"locator": "auto", "detail": f"downloaded {len(state['downloads'])} file(s): {names}"
                                         + (f" across {len(views)} result view(s)" if views else "")}


def _result_tabs(page) -> List[tuple]:
    """Visible tab controls of the result (2-12 distinct short labels), in page order."""
    try:
        loc = page.locator(_TAB_SELECTOR)
        seen, out = set(), []
        for i in range(min(loc.count(), 20)):
            el = loc.nth(i)
            label = (el.inner_text(timeout=1_000) or el.get_attribute("aria-label") or "").strip()
            if 0 < len(label) <= 40 and label not in seen:
                seen.add(label)
                out.append((el, label))
        return out if 2 <= len(out) <= 12 else []
    except Exception:
        return []


def _download_here(page, out: Path, state, wait_for_control: bool, limit: int) -> List[str]:
    """Click download/export controls in the current view; returns the labels tried."""
    clicked: List[str] = []
    end = time.monotonic() + (DOWNLOAD_LOCATE_TIMEOUT_MS / 1000 if wait_for_control else 0)
    while len(clicked) < limit:
        candidate = None
        try:  # one round trip: label + download attribute + enabled state of every visible control
            rows = page.evaluate(_CONTROLS_JS)
        except Exception:
            rows = []
        for i, label, has_dl, enabled in rows:
            label = (label or "").strip()[:80]
            is_dl = (has_dl or bool(_DOWNLOAD_TEXT.search(label))) and not _PRINT.search(label)
            if is_dl and enabled and (label or "(download link)") not in clicked:
                candidate = (page.locator(_CONTROL_SELECTOR).nth(i), label or "(download link)")
                break
        if candidate is None:
            if clicked or time.monotonic() > end:
                break
            page.wait_for_timeout(1_000)
            continue
        el, label = candidate
        clicked.append(label)
        try:
            with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS if not state["downloads"] else 30_000) as info:
                el.click(timeout=CLICK_TIMEOUT_MS)
            _save_download(info.value, out, state)
        except StepFailed:
            raise
        except Exception:
            page.wait_for_timeout(800)  # e.g. an "Export" menu opened instead: its items are tried next
    return clicked


_FOLLOW_UP_LABEL = re.compile(r"change|revis|feedback|request|instruction|refine|edit|prompt|message|comment", re.I)
_FOLLOW_UP_BUTTON = re.compile(r"\b(revise|regenerate|apply|update|submit|send|request|refine|save)\b", re.I)


def _follow_up(page, step: Dict[str, Any]) -> Dict[str, Any]:
    """Act on the generated result: type a follow-up (e.g. a change request) into the box that appeared after
    generating, and press its submit-like button. Boxes of the original form (known_labels) are skipped."""
    known = {(l or "").strip() for l in step.get("known_labels") or []}
    end = time.monotonic() + DOWNLOAD_LOCATE_TIMEOUT_MS / 1000
    while True:
        boxes = page.locator("textarea:visible, input[type=text]:visible, [contenteditable=true]:visible")
        pick = None
        for i in range(min(boxes.count(), 60)):
            el = boxes.nth(i)
            try:
                label = " ".join(filter(None, [el.get_attribute("placeholder"), el.get_attribute("aria-label"),
                                               el.get_attribute("name"), el.get_attribute("id")]))
                if label.strip() in known or not el.is_enabled():
                    continue
                if _FOLLOW_UP_LABEL.search(label) or pick is None:
                    pick = (el, label)
                    if _FOLLOW_UP_LABEL.search(label):
                        break
            except Exception:
                continue
        if pick or time.monotonic() > end:
            break
        page.wait_for_timeout(1_000)
    if not pick:
        raise StepFailed("no follow-up input (e.g. a change-request box) appeared after generating")
    el, label = pick
    el.fill(step.get("value") or "")
    container = el.locator("xpath=ancestor::*[self::form or self::section or self::div][1]")
    button = container.locator("button:visible").filter(has_text=_FOLLOW_UP_BUTTON)
    if not button.count():
        button = page.locator("button:visible").filter(has_text=_FOLLOW_UP_BUTTON)
    if button.count():
        button.first.click(timeout=CLICK_TIMEOUT_MS)
    else:
        el.press("Enter")
    return {"locator": "follow-up", "detail": f"sent the follow-up through “{label.strip()[:60] or 'text box'}”"}


def _locate(page, target: Dict[str, Any], timeout_ms: int):
    """In-page resolver (mirrors discovery) first, Playwright locators as fallback; retries while the UI renders."""
    token = f"t{time.monotonic_ns()}"
    label, text = target.get("label") or "", target.get("text") or ""
    end = time.monotonic() + timeout_ms / 1000
    while True:
        try:
            if page.evaluate(_RESOLVE_JS, [target, token]):
                return page.locator(f'[data-aqp-target="{token}"]').first, "discovery-match"
        except Exception:
            pass
        fallbacks = []
        if target.get("kind") == "field" and label:
            fallbacks += [("label", page.get_by_label(label, exact=True)), ("placeholder", page.get_by_placeholder(label, exact=True)),
                          ("label~", page.get_by_label(label))]
        if target.get("kind") == "field" and target.get("name"):
            fallbacks.append(("name", page.locator(f'[name="{_css(target["name"])}"]')))
        if target.get("kind") == "button" and text:
            fallbacks += [("role", page.get_by_role("button", name=text, exact=True)), ("role~", page.get_by_role("button", name=text))]
        if target.get("kind") == "link" and target.get("href"):
            fallbacks.append(("href", page.locator(f'a[href$="{_css(urllib.parse.urlsplit(target["href"]).path)}"]')))
        for how, loc in fallbacks:
            try:
                for i in range(min(loc.count(), 5)):
                    if loc.nth(i).is_visible():
                        return loc.nth(i), how
            except Exception:
                continue
        if time.monotonic() > end:
            raise StepFailed(f"element not found on {urllib.parse.urlsplit(page.url).path}: {_describe(target)}")
        page.wait_for_timeout(500)


def _settle(page, timeout_ms: int, inflight: Dict, state) -> Dict[str, Any]:
    """Wait until no loading indicator is shown and the page text stops changing (and requests finish)."""
    t0 = time.monotonic()
    end = t0 + timeout_ms / 1000
    last_len, stable = -1, 0
    page.wait_for_timeout(1_500)
    while time.monotonic() < end:
        try:
            busy, length = page.evaluate(_BUSY_JS)
        except Exception:
            busy, length = True, last_len  # navigating
        stable = stable + 1 if (length == last_len and not busy) else 0
        last_len = length
        if stable >= 3 and (not inflight or stable >= 6):
            break
        page.wait_for_timeout(1_000)
    else:
        raise StepFailed(f"the app was still busy after {timeout_ms // 1000}s")
    if state.get("baseline") is not None:
        state["reply"] = _new_text(state["baseline"], _body_text(page))
    return {"detail": f"settled after {time.monotonic() - t0:.1f}s"}


def _capture(page, ctx, live_url, step, out: Path, state) -> Dict[str, Any]:
    got = []
    try:
        page.screenshot(path=str(out / "screenshot.png"), full_page=True)
        state["screenshot"] = f"{out.name}/screenshot.png"
        got.append("screenshot")
    except Exception:
        pass
    try:
        text = _body_text(page)[:DOM_TEXT_LIMIT]
        (out / "dom.txt").write_text(text, encoding="utf-8")
        state["dom_text"], state["dom_excerpt"] = f"{out.name}/dom.txt", text[:EXCERPT]
        got.append("dom_text")
        if state.get("page_before") is not None and not (out / "dom_before.txt").exists():
            (out / "dom_before.txt").write_text(state["page_before"][:DOM_TEXT_LIMIT], encoding="utf-8")
            state["dom_before"] = f"{out.name}/dom_before.txt"
        if state.get("baseline") is not None and state.get("reply") is None:
            state["reply"] = _new_text(state["baseline"], text)
    except Exception:
        pass
    if state.get("reply"):
        got.append("reply")
    if state["downloads"]:
        got.append(f"{len(state['downloads'])} download(s)")
    if state.get("response"):
        got.append("response")
    return {"status": "passed" if got else "failed", "detail": "captured " + (", ".join(got) or "nothing")}


def _structural_assert(page, step) -> Dict[str, Any]:
    if step.get("kind") == "visible":
        n = page.locator("canvas:visible, svg:visible, table:visible").count()
        return {"status": "passed" if n else "failed", "detail": f"{n} chart/table element(s) visible"}
    return {"status": "deferred"}


def _http(ctx, live_url, step, out: Path, state) -> Dict[str, Any]:
    url = join_same_origin(live_url, step["path"])
    if not url:
        raise StepFailed(f"refused to call outside the live app's origin ({str(step['path'])[:80]})")
    t0 = time.monotonic()
    resp = ctx.request.fetch(url, method=step.get("method") or "POST", data=step.get("body"), timeout=120_000)
    body = resp.text()[:DOM_TEXT_LIMIT]
    (out / "response.txt").write_text(body, encoding="utf-8")
    state["response"] = {"status": resp.status, "ms": int((time.monotonic() - t0) * 1000),
                         "content_type": resp.headers.get("content-type"), "file": f"{out.name}/response.txt",
                         "excerpt": body[:EXCERPT]}
    if step.get("expect_status") == "2xx" and not 200 <= resp.status < 300:
        raise StepFailed(f"HTTP {resp.status} from {step['method']} {step['path']}")
    return {"detail": f"HTTP {resp.status} in {state['response']['ms']} ms"}


# ── helpers ─────────────────────────────────────────────────────────────────

def _quiet_networkidle(page, ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass


def _body_text(page) -> str:
    try:
        return page.inner_text("body", timeout=5_000)
    except Exception:
        return ""


def _new_text(before: str, after: str) -> Optional[str]:
    """Lines that appeared after sending, i.e. the reply (plus our own echoed message, which the judge tolerates)."""
    old = set(l.strip() for l in before.splitlines())
    new = [l for l in after.splitlines() if l.strip() and l.strip() not in old]
    return "\n".join(new)[:8000] or None


def _sniff(data: bytes, name: str) -> str:
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return {"docx": "docx", "xlsx": "xlsx", "pptx": "pptx"}.get(name.rsplit(".", 1)[-1].lower(), "zip")
    try:
        data[:2000].decode("utf-8")
        return name.rsplit(".", 1)[-1].lower() if "." in name else "text"
    except UnicodeDecodeError:
        return "binary"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "file"


def _css(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _describe(t: Dict[str, Any]) -> str:
    what = t.get("label") or t.get("text") or t.get("name") or t.get("href") or "?"
    return f"{t.get('kind', 'element')} “{what}”" + (f" in “{t['context'][:40]}”" if t.get("context") else "")


def _short(exc: Exception) -> str:
    msg = str(exc).split("\n")[0]
    return f"{type(exc).__name__}: {msg}"[:300] if not isinstance(exc, StepFailed) else msg[:300]


def _blocked(plan: Dict[str, Any], reason: str, status: str = "blocked") -> Dict[str, Any]:
    r = {k: plan.get(k) for k in ("plan_id", "test_id", "test_code", "criterion_code", "requirement_ref", "title",
                                  "class", "kind", "scored", "variant")}
    r.update(status=status, error=reason, failed_step=None, duration_ms=0, steps=[], captures={}, observations={},
             expectations=[])
    return r


def _one_line(r: Dict[str, Any]) -> str:
    name = r.get("test_code") or r["plan_id"]
    if r["status"] == "completed":
        caps = r["captures"]
        extra = [f"{len(caps['downloads'])} download(s)" if caps.get("downloads") else "", "reply captured" if caps.get("reply") else ""]
        return f"{name}: ran {len(r['steps'])} steps in {r['duration_ms'] / 1000:.1f}s" + \
            "".join(f" · {e}" for e in extra if e)
    return f"{name}: {r['status']}" + (f" at step {r['failed_step']}" if r.get("failed_step") else "") + f" — {r.get('error')}"


def _summary(status: str, results: List[Dict[str, Any]], started: float, reason: Optional[str] = None,
             login: Optional[Dict] = None) -> Dict[str, Any]:
    count = lambda s: sum(1 for r in results if r["status"] == s)  # noqa: E731
    return {"status": status, "reason": reason, "login": login or {"attempted": False},
            "duration_s": round(time.monotonic() - started, 1),
            "counts": {"plans": len(results), "completed": count("completed"), "failed": count("failed"),
                       "error": count("error"), "blocked": count("blocked"), "not_run": count("not_run"),
                       "downloads": sum(len((r.get("captures") or {}).get("downloads") or []) for r in results)},
            "results": results}

