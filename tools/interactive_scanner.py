"""
interactive_scanner.py — extends PlaywrightScanner with live user interaction.

Session loop:
  - Browser opens in non-headless mode
  - No auto-close timer — the browser stays open until the user closes it,
    or clicks the in-page "Finish Recording" banner injected by this module.
  - User can click around; blast-radius elements are auto-scanned around
    each click (see _scan_blast_radius / _BLAST_RADIUS_SCORES).
  - URL path changes create new page records.
  - On browser close (or explicit "Finish Recording"): save and exit.

Flow segmentation:
  - Idle gap > 8s between consecutive clicks
  - Two double-clicks within 3 seconds (user gesture = "new flow" boundary)

Crash safety: a checkpoint is flushed atomically to disk after every click
and on a periodic heartbeat (CHECKPOINT_INTERVAL_S). If the process is
killed mid-session, tools/discovery/interactive_dom_scan.py's
promote_checkpoint() can rebuild the same final artifacts from that
checkpoint alone, via _restore_from_checkpoint()/_build_result() below.

Outputs (returned dict + written by interactive_dom_scan.py):
  - Multi-page DOM elements (pages array + backward-compat elements root key)
  - Raw session event log (click events, API calls, page transitions)
  - User flows assembled from click sequence
  - Checkpoint file (written atomically on each significant event)
"""

import json
import logging
import os
import signal
import threading
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from playwright.sync_api import Page

from tools.playwright_scanner import PlaywrightScanner, _is_browser_closed_error


# ─────────────────────────────────────────────────────────────────────────────
# JavaScript injected via add_init_script (re-runs on every page load)
# ─────────────────────────────────────────────────────────────────────────────

_JS_CLICK_TRACKER = r"""
(function() {
    if (window.__qaClickTrackerInstalled) return;
    window.__qaClickTrackerInstalled = true;

    window.__qaBuildCssPath = function(el) {
        if (!el || el === document.body) return 'body';
        if (el.id) return '#' + CSS.escape(el.id);
        var path = '';
        var node = el;
        while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.body) {
            var name = node.nodeName.toLowerCase();
            var idx = 1;
            var sib = node.previousElementSibling;
            while (sib) {
                if (sib.nodeName === node.nodeName) idx++;
                sib = sib.previousElementSibling;
            }
            var part = idx > 1 ? name + ':nth-of-type(' + idx + ')' : name;
            path = path ? part + ' > ' + path : part;
            if (node.id) {
                path = '#' + CSS.escape(node.id) + ' > ' + path.split(' > ').slice(1).join(' > ');
                path = path.replace(/ > $/, '');
                break;
            }
            node = node.parentElement;
        }
        return path || el.nodeName.toLowerCase();
    };

    document.addEventListener('click', function(e) {
        var el = e.target;
        // Ignore clicks on our own recording overlay — it's not part of the
        // page under test and must not be captured as a user interaction.
        if (el && el.closest && el.closest('#__qa_rec_overlay')) return;
        try {
            window.__qaReportClick({
                css: window.__qaBuildCssPath(el),
                tag: el.tagName ? el.tagName.toLowerCase() : '',
                text: ((el.innerText || el.textContent || el.value || '')).substring(0, 120).trim(),
                href: el.href || '',
                ts: Date.now(),
                isTrusted: e.isTrusted
            });
        } catch(err) {}
    }, true);
})();
"""

# Small fixed-position "recording" banner injected into every page so the
# user can end the session explicitly (click "Finish Recording") instead of
# being forced to close the whole browser window to stop. Purely a UI
# convenience — closing the browser remains a working fallback via the
# existing page "close" / browser "disconnected" handlers.
_JS_RECORDING_OVERLAY = r"""
(function() {
    if (window.__qaOverlayInstalled) return;
    window.__qaOverlayInstalled = true;

    function build() {
        var bar = document.createElement('div');
        bar.id = '__qa_rec_overlay';
        bar.style.cssText = 'position:fixed;bottom:12px;right:12px;z-index:2147483647;' +
            'background:#1a1a1a;color:#fff;font:12px/1.4 sans-serif;padding:8px 12px;' +
            'border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.4);display:flex;' +
            'align-items:center;gap:10px;';

        var dot = document.createElement('span');
        dot.style.cssText = 'width:8px;height:8px;border-radius:50%;background:#e11;display:inline-block;';

        var label = document.createElement('span');
        label.id = '__qa_rec_status';
        label.textContent = 'REC · 0 elements · 0 clicks';

        var btn = document.createElement('button');
        btn.textContent = 'Finish Recording';
        btn.style.cssText = 'background:#0073EA;color:#fff;border:none;border-radius:4px;' +
            'padding:4px 10px;cursor:pointer;font:inherit;';
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            try { window.__qaFinishRecording(); } catch (err) {}
            label.textContent = 'Finishing...';
            btn.disabled = true;
        });

        bar.appendChild(dot);
        bar.appendChild(label);
        bar.appendChild(btn);
        document.documentElement.appendChild(bar);
    }

    window.__qaUpdateOverlayStatus = function(elementCount, clickCount) {
        var label = document.getElementById('__qa_rec_status');
        if (label) label.textContent = 'REC · ' + elementCount + ' elements · ' + clickCount + ' clicks';
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', build);
    } else {
        build();
    }
})();
"""

# JavaScript to find the semantic container of a clicked element.
# Returns {css, containerTag} so Python can compute a blast-radius score.
_BLAST_RADIUS_JS = r"""
(cssPath) => {
    var el;
    try { el = document.querySelector(cssPath); } catch(e) { return null; }
    if (!el) return null;

    var CONTAINER_TAGS = new Set(['form','nav','section','article','main','aside','header','footer','dialog','fieldset','search']);
    var CONTAINER_ROLES = new Set(['dialog','navigation','main','complementary','form','search','region','group']);

    var node = el.parentElement;
    var foundTag = '';
    for (var i = 0; i < 4 && node && node !== document.body; i++) {
        var tag = (node.tagName || '').toLowerCase();
        var role = (node.getAttribute('role') || '').toLowerCase();
        if (CONTAINER_TAGS.has(tag) || CONTAINER_ROLES.has(role)) {
            foundTag = CONTAINER_ROLES.has(role) ? role : tag;
            break;
        }
        node = node.parentElement;
    }
    if (!node || node === document.body) node = el.parentElement;
    if (!node) return null;

    return {css: window.__qaBuildCssPath(node), containerTag: foundTag};
}
"""

# Blast-radius score by container type.
# Only elements whose container scores > _BLAST_SCORE_THRESHOLD (0.5) are kept.
_BLAST_RADIUS_SCORES: Dict[str, float] = {
    # Tight functional groupings — everything inside a form/dialog is highly related
    "form":          0.90,
    "fieldset":      0.90,
    "dialog":        0.90,
    # Navigation and landmark groups
    "nav":           0.75,
    "navigation":    0.75,
    "header":        0.75,
    "footer":        0.75,
    "search":        0.75,
    # Content sections — moderate relationship
    "section":       0.65,
    "article":       0.65,
    "region":        0.65,
    # Broad page regions — weak relationship, below threshold
    "main":          0.45,
    "aside":         0.45,
    "complementary": 0.45,
    "group":         0.45,
}
_BLAST_SCORE_THRESHOLD = 0.50


def _blast_radius_score(container_tag: str, elem_tag: str, clicked_tag: str) -> float:
    """Return a 0–1 relevance score for an element found via blast-radius scan."""
    base = _BLAST_RADIUS_SCORES.get((container_tag or "").lower(), 0.35)
    # Small bonus when the found element is the same interactive type as what was clicked
    if elem_tag and clicked_tag and elem_tag == clicked_tag:
        base = min(base + 0.05, 1.0)
    return base

_INTERACTIVE_SELECTORS = ["input", "button", "select", "textarea", "a", "[role=combobox]"]

_SCENARIO_TYPE_KEYWORDS: Dict[str, Set[str]] = {
    "authentication": {"login", "signin", "sign_in", "password", "logout", "signup", "register"},
    "search":         {"search", "filter", "sort", "query", "find"},
    "purchase":       {"cart", "buy", "checkout", "purchase", "order", "pay"},
    "navigation":     {"menu", "nav", "home", "about", "contact", "back", "next"},
    "form_submission": {"submit", "send", "save", "update", "create", "delete", "confirm"},
}


# ─────────────────────────────────────────────────────────────────────────────
# InteractiveScanner
# ─────────────────────────────────────────────────────────────────────────────

class InteractiveScanner(PlaywrightScanner):
    """
    UI scanner with live user interaction support.

    Inherits all element-extraction helpers from PlaywrightScanner.
    Overrides the scan loop to run an interactive session instead of
    a fixed 30-second automated capture.
    """

    CHECKPOINT_INTERVAL_S = 20
    FLOW_IDLE_GAP_S = 8.0
    DOUBLE_CLICK_MS = 300
    DOUBLE_DOUBLE_S = 3.0

    # Once the browser is known to be closing (close/disconnect event fired,
    # _stop_event set), a single blocked Playwright call (e.g. a page.evaluate
    # in flight exactly when the connection dies) can still prevent the
    # session loop or close() from returning even though the event itself
    # fired promptly. This bounds how long we wait for a graceful finish
    # after that point before abandoning the thread and moving on with
    # whatever data was already captured.
    _CLOSE_GRACE_S = 10

    def __init__(self, browser_name: str = "chromium"):
        super().__init__(browser_name=browser_name, headless=False)
        self.logger = logging.getLogger("workflow.interactive_scanner")

        # Thread-safe click queue (expose_function fires on Playwright internal thread)
        self._click_queue: List[Dict] = []
        self._click_lock = threading.Lock()

        # Session stop signal (set only by timer or disconnect handlers — never from Playwright thread)
        self._stop_event = threading.Event()
        self._end_reason_override: Optional[str] = None
        self._checkpoint_timer: Optional[threading.Timer] = None
        self._user_clicked = False

        # Counters (global across all sessions/pages)
        self._page_loc_counter = 1
        self._page_counter = 1
        self._global_seq = 0

        # Current page accumulation
        self._current_path = "/"
        self._current_page_elements: List[Dict] = []
        self._current_page_seen: Set[str] = set()
        self._current_page_clicks: List[str] = []

        # Final output accumulators
        self._pages: List[Dict] = []
        self._all_click_events: List[Dict] = []
        self._all_api_calls: List[Dict] = []
        self._all_page_transitions: List[Dict] = []
        self._session_records: List[Dict] = []

        self._checkpoint_path = ""
        self._base_url = ""

        # Signal handler originals
        self._orig_sigint = None
        self._orig_sigterm = None

    # ─────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────

    def scan_interactive(
        self,
        url: str,
        checkpoint_path: str = "",
        resume_data: Optional[Dict] = None,
        storage_state_path: Optional[str] = None,
        auth_config: Optional[dict] = None,
        setup_steps: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Run an interactive scanning session until the user closes the browser
        or clicks the in-page "Finish Recording" banner.

        Returns a dict containing multi-page element data, session events,
        and assembled user flows.  Written files are handled by
        interactive_dom_scan.py (which calls this method).
        """
        self._base_url = url
        self._checkpoint_path = checkpoint_path

        if resume_data:
            self._restore_from_checkpoint(resume_data)

        self._register_signals()
        try:
            self._run_worker_bounded(url, storage_state_path, auth_config, setup_steps)
        finally:
            self._cancel_timers()
            self._restore_signals()

        # Finalize any page elements still in-progress
        if self._current_page_elements or self._current_page_clicks:
            self._finalize_current_page(full_url=url)

        if self._checkpoint_path:
            self._flush_checkpoint(status="complete")
            last_session = self._session_records[-1] if self._session_records else {}
            if last_session.get("end_reason") in ("user_closed", "finished"):
                try:
                    os.remove(self._checkpoint_path)
                except OSError:
                    pass

        return self._build_result(url)

    def _run_worker_bounded(
        self,
        url: str,
        storage_state_path: Optional[str],
        auth_config: Optional[dict],
        setup_steps: Optional[list],
    ) -> None:
        """Run launch → setup steps → tracking → session loop → close all on
        one dedicated worker thread.

        Playwright's sync API is bound via greenlet to whichever OS thread
        calls sync_playwright().start() — every later call (goto, evaluate,
        query_selector_all, close, ...) must happen on that same thread or it
        raises "Cannot switch to a different thread". Launching on the
        caller's thread and then running the session loop or close() on
        separate threads breaks that invariant on every Playwright call made
        from those threads. Keeping the whole lifecycle on one worker thread
        fixes that while still letting the caller bound how long it waits
        before giving up on a wedged call.

        No cap while the session is genuinely active (browser still open);
        once _stop_event fires, only _CLOSE_GRACE_S more seconds are granted
        before the thread is abandoned and we move on with whatever data was
        already captured.
        """
        def _target() -> None:
            try:
                page = self.launch(storage_state_path=storage_state_path, auth_config=auth_config)
                if setup_steps:
                    self.logger.info(f"  Running {len(setup_steps)} setup step(s) before interactive session")
                    self._execute_setup_steps(page, setup_steps)
                    self.logger.info("  Setup steps complete — starting interactive session")

                self._setup_tracking(page)
                self._run_sessions(page, url)
            except Exception as exc:
                if not _is_browser_closed_error(exc):
                    self.logger.error(f"InteractiveScanner unexpected error: {exc}", exc_info=True)
            finally:
                # Guarantee the outer loop transitions to its bounded wait
                # even if launch()/_run_sessions() ended for a reason that
                # never routed through the close/disconnect handlers (e.g. an
                # unexpected exception) — close() below must still run on
                # this same thread, so the caller needs a reliable signal
                # that it's time to stop waiting unboundedly.
                self._stop_event.set()
                try:
                    self.close()
                except Exception:
                    pass

        t = threading.Thread(target=_target, name="interactive-scanner-session", daemon=True)
        t.start()
        while t.is_alive() and not self._stop_event.is_set():
            t.join(timeout=0.2)
        if t.is_alive():
            t.join(timeout=self._CLOSE_GRACE_S)
            if t.is_alive():
                self.logger.warning(
                    f"  Browser closed but the session thread did not finish "
                    f"finalizing within {self._CLOSE_GRACE_S}s (likely a "
                    "Playwright call blocked on the dead connection) — "
                    "abandoning it and building the result from data captured so far"
                )

    # ─────────────────────────────────────────────────────────────────
    # Session loop
    # ─────────────────────────────────────────────────────────────────

    def _run_sessions(self, page: Page, base_url: str) -> None:
        session_number = len(self._session_records) + 1

        self._stop_event.clear()
        self._user_clicked = False
        session_start_mono = time.monotonic()
        session_start_wall = time.time()

        # No auto-close timer — browser stays open until the user closes it
        # or clicks "Finish Recording". Checkpoint heartbeat still runs
        # every CHECKPOINT_INTERVAL_S seconds.
        self._schedule_checkpoint_heartbeat()

        # Navigate to base URL
        try:
            page.goto(base_url, wait_until="commit", timeout=30000)
        except Exception as exc:
            self.logger.warning(f"Session {session_number} navigation: {exc}")

        self._poll_page_ready(page, max_wait_s=15, poll_s=1.0)

        # Reset page accumulators for this session
        try:
            self._current_path = _path_of(page.url)
        except Exception:
            self._current_path = _path_of(base_url)

        self._current_page_elements = []
        self._current_page_seen = set()
        self._current_page_clicks = []

        # Initial element capture
        initial_elements = self._scan_current_page(page)
        self._current_page_elements.extend(initial_elements)

        if self._checkpoint_path:
            self._flush_checkpoint(status="in_progress")

        self._update_overlay_status(page)

        session_click_events: List[Dict] = []
        session_transitions: List[Dict] = []

        # ── Inner poll loop ──────────────────────────────────────
        while not self._stop_event.is_set():
            # Health check — detect silent browser close
            try:
                if page.is_closed():
                    self._stop_event.set()
                    break
            except Exception as exc:
                if _is_browser_closed_error(exc):
                    self._stop_event.set()
                    break

            # Drain click queue (clicks arrive from JS callback thread)
            with self._click_lock:
                pending = list(self._click_queue)
                self._click_queue.clear()

            for click_raw in pending:
                if not self._user_clicked:
                    self._user_clicked = True
                    self.logger.info("First user interaction detected — browser will stay open until manually closed or Finish Recording is clicked")

                self._global_seq += 1
                current_page_id = f"PAGE-{self._page_counter:03d}"
                click_event = {
                    **click_raw,
                    "seq": self._global_seq,
                    "page_id": current_page_id,
                    "page_path": self._current_path,
                    "ts_offset_ms": int((time.monotonic() - session_start_mono) * 1000),
                }

                # Check for URL / path change after click
                try:
                    time.sleep(0.15)  # brief settle for SPA routing
                    new_url = page.url
                    new_path = _path_of(new_url)
                    if new_path != self._current_path:
                        transition = {
                            "from_path": self._current_path,
                            "to_path": new_path,
                            "triggered_by_seq": self._global_seq,
                            "ts_offset_ms": click_event["ts_offset_ms"],
                        }
                        session_transitions.append(transition)
                        self._all_page_transitions.append(transition)

                        # Finalize old page before switching
                        self._finalize_current_page(full_url=new_url)

                        # Set up new page accumulators
                        self._current_path = new_path
                        self._current_page_elements = []
                        self._current_page_seen = set()
                        self._current_page_clicks = []
                        current_page_id = f"PAGE-{self._page_counter:03d}"

                        # Wait for new page DOM, then scan
                        self._poll_page_ready(page, max_wait_s=8, poll_s=1.0)
                        new_elements = self._scan_current_page(page)
                        self._current_page_elements.extend(new_elements)

                        # Update click event with corrected page_id and path
                        click_event["page_id"] = current_page_id
                        click_event["page_path"] = new_path
                except Exception:
                    pass

                # Find locator_id for the clicked CSS
                matched_loc = self._css_to_loc_id(click_event.get("css", ""))
                click_event["locator_id"] = matched_loc
                if matched_loc and matched_loc not in self._current_page_clicks:
                    self._current_page_clicks.append(matched_loc)

                session_click_events.append(click_event)
                self._all_click_events.append(click_event)

                # Blast radius scan around the clicked element
                blast = self._scan_blast_radius(page, click_event.get("css", ""), matched_loc)
                self._current_page_elements.extend(blast)

                if self._checkpoint_path:
                    self._flush_checkpoint(status="in_progress")

                self._update_overlay_status(page)

            if not self._stop_event.is_set():
                time.sleep(0.3)
        # ── End inner loop ───────────────────────────────────────

        end_reason = self._end_reason_override or "user_closed"

        # Finalize the page the user ended on
        try:
            final_url = page.url
        except Exception:
            final_url = base_url
        self._finalize_current_page(full_url=final_url)

        # Record session
        self._session_records.append({
            "session_number": session_number,
            "start_time": session_start_wall,
            "end_time": time.time(),
            "end_reason": end_reason,
            "click_events": session_click_events,
            "page_transitions": session_transitions,
        })

        self.logger.info(
            f"Session {session_number} ended: reason={end_reason} "
            f"clicks={len(session_click_events)} transitions={len(session_transitions)}"
        )

    # ─────────────────────────────────────────────────────────────────
    # JS injection and event callbacks
    # ─────────────────────────────────────────────────────────────────

    def _setup_tracking(self, page: Page) -> None:
        # expose_function persists across same-page navigations
        try:
            page.expose_function("__qaReportClick", self._on_user_click)
        except Exception:
            pass
        try:
            page.expose_function("__qaFinishRecording", self._on_finish_recording)
        except Exception:
            pass

        page.add_init_script(_JS_CLICK_TRACKER)
        page.add_init_script(_JS_RECORDING_OVERLAY)
        page.on("request", self._on_request)

        # Disconnect / crash / close handlers — these set _stop_event from a
        # background thread safely. page "close" fires the instant the tab/
        # window closes; browser "disconnected" additionally covers the whole
        # process going away — some apps (e.g. post-login pages holding open
        # WebSocket/service-worker connections) can delay full process
        # teardown, so page-level "close" is the faster, more direct signal
        # and must not be missed just because "disconnected" is slower.
        try:
            self.browser.on("disconnected", self._handle_disconnect)
        except Exception:
            pass
        page.on("close", self._handle_page_close)
        page.on("crash", self._handle_crash)

    def _on_user_click(self, data: Dict) -> None:
        """JS expose_function callback — may run on Playwright's internal thread."""
        with self._click_lock:
            self._click_queue.append({
                "css":          data.get("css", ""),
                "tag":          data.get("tag", ""),
                "display_text": data.get("text", ""),
                "href":         data.get("href", ""),
                "ts_ms":        data.get("ts", 0),
                "is_trusted":   data.get("isTrusted", True),
            })

    def _on_request(self, request) -> None:
        """Capture XHR / fetch calls for API observation."""
        try:
            if request.resource_type in ("xhr", "fetch", "websocket"):
                self._all_api_calls.append({
                    "url":       request.url,
                    "method":    request.method,
                    "after_seq": self._global_seq,
                    "page_path": self._current_path,
                })
        except Exception:
            pass

    def _handle_disconnect(self) -> None:
        self.logger.info("Browser disconnected — flushing and stopping")
        if self._checkpoint_path:
            try:
                self._flush_checkpoint(status="crashed")
            except Exception:
                pass
        self._stop_event.set()

    def _handle_page_close(self) -> None:
        self.logger.info("Page closed — flushing and stopping")
        if self._checkpoint_path:
            try:
                self._flush_checkpoint(status="complete")
            except Exception:
                pass
        self._stop_event.set()

    def _handle_crash(self) -> None:
        self.logger.warning("Page crashed — flushing and stopping")
        if self._checkpoint_path:
            try:
                self._flush_checkpoint(status="crashed")
            except Exception:
                pass
        self._stop_event.set()

    def _on_finish_recording(self) -> None:
        """User clicked the in-page "Finish Recording" banner — end the
        session the same way a browser close does, without requiring the
        user to actually close the window."""
        self.logger.info("Finish Recording clicked — flushing and stopping")
        self._end_reason_override = "finished"
        if self._checkpoint_path:
            try:
                self._flush_checkpoint(status="complete")
            except Exception:
                pass
        self._stop_event.set()

    def _update_overlay_status(self, page: Page) -> None:
        """Refresh the in-page recording banner's live element/click counts."""
        try:
            page.evaluate(
                "([n, c]) => { if (window.__qaUpdateOverlayStatus) window.__qaUpdateOverlayStatus(n, c); }",
                [len(self._current_page_elements), len(self._current_page_clicks)],
            )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────
    # Element scanning
    # ─────────────────────────────────────────────────────────────────

    def _scan_current_page(self, page: Page) -> List[Dict]:
        """Scan all interactive elements on the current page."""
        elements = []
        for selector in _INTERACTIVE_SELECTORS:
            try:
                handles = page.query_selector_all(selector)
            except Exception:
                continue
            for handle in handles:
                try:
                    data = self._get_element_data(handle)
                    css = (data.get("technical_locators") or {}).get("css", "")
                    if not css or css in self._current_page_seen:
                        continue
                    self._current_page_seen.add(css)
                    loc_id = f"LOC-{self._page_loc_counter:04d}"
                    self._page_loc_counter += 1
                    elements.append({
                        "locator_id": loc_id,
                        "page_id": f"PAGE-{self._page_counter:03d}",
                        "blast_radius_source": None,
                        "blast_radius_score": None,
                        "tag": selector.replace("[role=combobox]", "combobox"),
                        **data,
                    })
                except Exception:
                    continue
        return elements

    def _scan_blast_radius(
        self,
        page: Page,
        click_css: str,
        clicked_loc_id: Optional[str],
    ) -> List[Dict]:
        """Scan interactive descendants of the semantic container around the clicked element.

        Only elements whose blast_radius_score > _BLAST_SCORE_THRESHOLD (0.50) are kept.
        The score is based on the container's semantic type:
          form/fieldset/dialog → 0.90  (included)
          nav/header/footer    → 0.75  (included)
          section/article      → 0.65  (included)
          main/aside           → 0.45  (excluded — too broad to be meaningful)
          no container found   → 0.35  (excluded)
        """
        if not click_css:
            return []
        try:
            container_info = page.evaluate(_BLAST_RADIUS_JS, click_css)
        except Exception:
            return []
        if not container_info:
            return []

        # JS now returns {css, containerTag} — handle both old string and new dict form
        if isinstance(container_info, dict):
            container_css = container_info.get("css", "")
            container_tag = container_info.get("containerTag", "")
        else:
            container_css = container_info
            container_tag = ""

        if not container_css:
            return []

        # Find clicked element's tag to compute same-type bonus
        clicked_tag = ""
        for el in self._current_page_elements:
            if (el.get("technical_locators") or {}).get("css", "") == click_css:
                clicked_tag = el.get("tag", "")
                break

        new_elements = []
        for selector in _INTERACTIVE_SELECTORS:
            elem_tag = selector.replace("[role=combobox]", "combobox")
            score = _blast_radius_score(container_tag, elem_tag, clicked_tag)
            if score <= _BLAST_SCORE_THRESHOLD:
                continue  # skip entire selector class — container is too broad

            try:
                handles = page.query_selector_all(f"{container_css} {selector}")
            except Exception:
                continue
            for handle in handles:
                try:
                    data = self._get_element_data(handle)
                    css = (data.get("technical_locators") or {}).get("css", "")
                    if not css or css in self._current_page_seen:
                        continue
                    self._current_page_seen.add(css)
                    loc_id = f"LOC-{self._page_loc_counter:04d}"
                    self._page_loc_counter += 1
                    new_elements.append({
                        "locator_id":       loc_id,
                        "page_id":          f"PAGE-{self._page_counter:03d}",
                        "blast_radius_source": clicked_loc_id,
                        "blast_radius_score":  round(score, 2),
                        "tag":              elem_tag,
                        **data,
                    })
                except Exception:
                    continue
        return new_elements

    def _css_to_loc_id(self, css: str) -> Optional[str]:
        """Find the locator_id of the element with the given CSS in the current page."""
        if not css:
            return None
        for el in self._current_page_elements:
            if (el.get("technical_locators") or {}).get("css", "") == css:
                return el.get("locator_id")
        return None

    # ─────────────────────────────────────────────────────────────────
    # Page finalization
    # ─────────────────────────────────────────────────────────────────

    def _finalize_current_page(self, full_url: str) -> None:
        """Save current page element data to _pages. Handles duplicate paths by merging."""
        if not self._current_page_elements and not self._current_page_clicks:
            return

        path = self._current_path or "/"
        page_id = f"PAGE-{self._page_counter:03d}"

        # Merge into existing page record if this path was already seen
        existing = next((p for p in self._pages if p["path"] == path), None)
        if existing:
            seen_in_existing = {
                (el.get("technical_locators") or {}).get("css", "")
                for el in existing["elements"]
            }
            for el in self._current_page_elements:
                css = (el.get("technical_locators") or {}).get("css", "")
                if css and css not in seen_in_existing:
                    seen_in_existing.add(css)
                    existing["elements"].append(el)
                    existing["element_count"] += 1
            for loc in self._current_page_clicks:
                if loc not in existing["user_clicked_locators"]:
                    existing["user_clicked_locators"].append(loc)
        else:
            self._pages.append({
                "page_id": page_id,
                "page_name": _page_name_from_path(path),
                "path": path,
                "url": full_url,
                "element_count": len(self._current_page_elements),
                "user_clicked_locators": list(self._current_page_clicks),
                "elements": list(self._current_page_elements),
            })
            self._page_counter += 1

        if self._checkpoint_path:
            self._flush_checkpoint(status="in_progress")

    # ─────────────────────────────────────────────────────────────────
    # User flow assembly
    # ─────────────────────────────────────────────────────────────────

    def _assemble_user_flows(self) -> List[Dict]:
        """
        Convert raw click events into segmented user flows.

        Boundaries:
          - Idle gap > FLOW_IDLE_GAP_S between consecutive clicks
          - Two double-clicks (each <= DOUBLE_CLICK_MS apart) within DOUBLE_DOUBLE_S
          - New scan session (handled by session_records boundary)
        """
        if not self._all_click_events:
            return []

        flows: List[Dict] = []
        flow_counter = 1
        current_steps: List[Dict] = []
        prev_ts_ms: Optional[int] = None
        prev_click_ts_for_dbl: Optional[int] = None
        first_dbl_ts: Optional[int] = None  # timestamp of first double-click in a pair

        def _commit_flow(steps: List[Dict]) -> None:
            nonlocal flow_counter
            if len(steps) < 1:
                return
            name, stype = _infer_flow_name(steps)
            pages_seen = list(dict.fromkeys(s.get("page_id", "") for s in steps))
            flows.append({
                "flow_id": f"FLOW-{flow_counter:03d}",
                "inferred_name": name,
                "inferred_scenario_type": stype,
                "confidence": 0.95,
                "pages_involved": [p for p in pages_seen if p],
                "steps": [
                    {
                        "step": i + 1,
                        "seq": s.get("seq"),
                        "locator_id": s.get("locator_id"),
                        "action": _infer_action_from_tag(s.get("tag", "")),
                        "display_text": s.get("display_text", ""),
                        "page_id": s.get("page_id", ""),
                        "page_path": s.get("page_path", ""),
                    }
                    for i, s in enumerate(steps)
                ],
                "api_calls_observed": [],
                "can_generate_test_case_directly": len(steps) >= 2,
            })
            flow_counter += 1

        for click in self._all_click_events:
            ts_ms = click.get("ts_ms", 0)

            # Double-click detection (two clicks within DOUBLE_CLICK_MS)
            is_double = (
                prev_click_ts_for_dbl is not None
                and ts_ms > 0
                and (ts_ms - prev_click_ts_for_dbl) <= self.DOUBLE_CLICK_MS
            )
            prev_click_ts_for_dbl = ts_ms

            if is_double:
                if first_dbl_ts is not None and (ts_ms - first_dbl_ts) / 1000.0 <= self.DOUBLE_DOUBLE_S:
                    # Double-double-click boundary gesture
                    _commit_flow(current_steps)
                    current_steps = []
                    first_dbl_ts = None
                else:
                    first_dbl_ts = ts_ms

            # Idle gap boundary
            if prev_ts_ms is not None and ts_ms > 0 and prev_ts_ms > 0:
                gap_s = (ts_ms - prev_ts_ms) / 1000.0
                if gap_s > self.FLOW_IDLE_GAP_S:
                    _commit_flow(current_steps)
                    current_steps = []

            current_steps.append(click)
            prev_ts_ms = ts_ms

        _commit_flow(current_steps)
        self._attach_api_calls_to_flows(flows)
        return flows

    def _attach_api_calls_to_flows(self, flows: List[Dict]) -> None:
        if not flows or not self._all_api_calls:
            return
        for api_call in self._all_api_calls:
            seq = api_call.get("after_seq", 0)
            best = None
            for flow in flows:
                seqs = [s.get("seq") for s in flow["steps"] if s.get("seq") is not None]
                if seqs and min(seqs) <= seq <= max(seqs) + 5:
                    best = flow
                    break
            if best is None and flows:
                best = flows[-1]
            if best:
                entry = {"url": api_call.get("url", ""), "method": api_call.get("method", "")}
                if entry not in best["api_calls_observed"]:
                    best["api_calls_observed"].append(entry)

    # ─────────────────────────────────────────────────────────────────
    # Checkpoint (atomic write via .tmp rename)
    # ─────────────────────────────────────────────────────────────────

    def _flush_checkpoint(self, status: str = "in_progress") -> None:
        if not self._checkpoint_path:
            return
        try:
            data = {
                "status": status,
                "checkpoint_at": time.time(),
                "base_url": self._base_url,
                "pages": self._pages,
                "current_path": self._current_path,
                "current_page_elements": self._current_page_elements,
                "current_page_clicks": self._current_page_clicks,
                "all_click_events": self._all_click_events,
                "all_api_calls": self._all_api_calls,
                "all_page_transitions": self._all_page_transitions,
                "loc_counter": self._page_loc_counter,
                "page_counter": self._page_counter,
                "global_seq": self._global_seq,
            }
            os.makedirs(os.path.dirname(os.path.abspath(self._checkpoint_path)), exist_ok=True)
            tmp = self._checkpoint_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._checkpoint_path)
        except Exception as exc:
            self.logger.warning(f"Checkpoint write failed: {exc}")

    def _restore_from_checkpoint(self, data: Dict) -> None:
        self._pages = data.get("pages", [])
        self._current_path = data.get("current_path", "/")
        self._current_page_elements = data.get("current_page_elements", [])
        self._current_page_seen = {
            (el.get("technical_locators") or {}).get("css", "")
            for el in self._current_page_elements
            if (el.get("technical_locators") or {}).get("css", "")
        }
        self._current_page_clicks = data.get("current_page_clicks", [])
        self._all_click_events = data.get("all_click_events", [])
        self._all_api_calls = data.get("all_api_calls", [])
        self._all_page_transitions = data.get("all_page_transitions", [])
        self._page_loc_counter = data.get("loc_counter", 1)
        self._page_counter = data.get("page_counter", 1)
        self._global_seq = data.get("global_seq", 0)
        self.logger.info(
            f"Resumed from checkpoint: {len(self._pages)} page(s), "
            f"{len(self._all_click_events)} click event(s)"
        )

    def _schedule_checkpoint_heartbeat(self) -> None:
        if not self._checkpoint_path:
            return

        def _beat() -> None:
            if not self._stop_event.is_set():
                self._flush_checkpoint(status="in_progress")
                self._schedule_checkpoint_heartbeat()

        self._checkpoint_timer = threading.Timer(self.CHECKPOINT_INTERVAL_S, _beat)
        self._checkpoint_timer.daemon = True
        self._checkpoint_timer.start()

    # ─────────────────────────────────────────────────────────────────
    # Signal handling
    # ─────────────────────────────────────────────────────────────────

    def _register_signals(self) -> None:
        # signal.signal() only works when called from the main thread — when
        # the interactive scan runs on a background thread (e.g. discovery's
        # parallel comprehension/DOM-scan step), this silently fails and
        # Ctrl+C never reaches _on_signal at all. Surface that instead of
        # swallowing it, since it means the graceful-stop path is unavailable
        # for this run and a wedged session can only be recovered by killing
        # the process.
        try:
            self._orig_sigint = signal.signal(signal.SIGINT, self._on_signal)
            self._orig_sigterm = signal.signal(signal.SIGTERM, self._on_signal)
        except (OSError, ValueError) as exc:
            self.logger.warning(
                f"  Could not register signal handlers ({exc}) — likely running "
                "on a background thread. Ctrl+C will not gracefully stop this "
                "interactive session; the process must be killed if it hangs."
            )

    def _restore_signals(self) -> None:
        try:
            if self._orig_sigint:
                signal.signal(signal.SIGINT, self._orig_sigint)
            if self._orig_sigterm:
                signal.signal(signal.SIGTERM, self._orig_sigterm)
        except (OSError, ValueError):
            pass

    def _on_signal(self, signum, frame) -> None:
        self.logger.info(f"Signal {signum} — flushing checkpoint and stopping")
        if self._checkpoint_path:
            try:
                self._flush_checkpoint(status="interrupted")
            except Exception:
                pass
        self._stop_event.set()

    # ─────────────────────────────────────────────────────────────────
    # Timer cleanup
    # ─────────────────────────────────────────────────────────────────

    def _cancel_timers(self) -> None:
        if self._checkpoint_timer:
            try:
                self._checkpoint_timer.cancel()
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────
    # Result assembly
    # ─────────────────────────────────────────────────────────────────

    def _build_result(self, url: str) -> Dict[str, Any]:
        all_elements = [el for pg in self._pages for el in pg.get("elements", [])]
        user_flows = self._assemble_user_flows()

        return {
            "url": url,
            "scan_mode": "interactive",
            "total_element_count": len(all_elements),
            # backward-compat key: first page elements (or empty)
            "elements": self._pages[0]["elements"] if self._pages else [],
            "element_count": len(all_elements),
            "pages": self._pages,
            "_session_data": {
                "sessions": self._session_records,
                "all_click_events": self._all_click_events,
                "all_api_calls": self._all_api_calls,
                "all_page_transitions": self._all_page_transitions,
            },
            "_user_flows": user_flows,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def _path_of(url: str) -> str:
    try:
        return urlparse(url).path.rstrip("/") or "/"
    except Exception:
        return "/"


def _page_name_from_path(path: str) -> str:
    cleaned = path.strip("/").replace("/", "_").replace("-", "_") or "home"
    return cleaned[:40]


def _infer_flow_name(steps: List[Dict]) -> tuple:
    texts = " ".join((s.get("display_text") or "").lower() for s in steps)
    for stype, keywords in _SCENARIO_TYPE_KEYWORDS.items():
        if any(kw in texts for kw in keywords):
            return stype.replace("_", " ").title(), stype
    first = steps[0].get("display_text") or steps[0].get("tag") or "element"
    return f"Interact with {first}", "general"


def _infer_action_from_tag(tag: str) -> str:
    if tag in ("input", "textarea"):
        return "fill"
    if tag == "select":
        return "select"
    return "click"
