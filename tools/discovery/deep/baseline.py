"""
baseline.py — console errors, page errors, failed requests and navigation timing per state
(task 2.7). Later phases (P4 consoleGuard, P7 performance) diff test runs against this file
so they can tell new errors and regressions apart from noise that already existed.
"""

import urllib.parse
from typing import Any, Callable, Dict, List, Optional

MAX_TEXT = 300
MAX_PER_KIND = 30

TIMING_JS = r"""() => {
  const n = performance.getEntriesByType('navigation')[0];
  const fcp = performance.getEntriesByName('first-contentful-paint')[0];
  const r = v => (typeof v === 'number' && isFinite(v)) ? Math.round(v) : null;
  if (!n) return null;
  return { ttfb_ms: r(n.responseStart), dcl_ms: r(n.domContentLoadedEventEnd), load_ms: r(n.loadEventEnd),
           fcp_ms: fcp ? r(fcp.startTime) : null, transfer_bytes: r(n.transferSize),
           requests: performance.getEntriesByType('resource').length + 1 };
}"""


class BaselineRecorder:
    """Buffers page signals between begin() and snapshot(). Attach once per page."""

    def __init__(self, url_allowed: Callable[[str], bool]):
        self.url_allowed = url_allowed
        self._buf: Dict[str, List[Dict[str, Any]]] = self._empty()

    @staticmethod
    def _empty() -> Dict[str, List[Dict[str, Any]]]:
        return {"console_errors": [], "console_warnings": [], "page_errors": [], "failed_requests": []}

    def attach(self, page) -> None:
        page.on("console", self._on_console)
        page.on("pageerror", self._on_pageerror)
        page.on("requestfailed", self._on_request_failed)
        page.on("response", self._on_response)

    def begin(self) -> None:
        self._buf = self._empty()

    def _add(self, kind: str, item: Dict[str, Any]) -> None:
        if len(self._buf[kind]) < MAX_PER_KIND and item not in self._buf[kind]:
            self._buf[kind].append(item)

    def _on_console(self, msg) -> None:
        try:
            if msg.type not in ("error", "warning"):
                return
            loc = msg.location or {}
            item = {"text": (msg.text or "")[:MAX_TEXT],
                    "source": f"{loc.get('url', '')}:{loc.get('lineNumber', '')}".strip(":")}
            self._add("console_errors" if msg.type == "error" else "console_warnings", item)
        except Exception:
            pass

    def _on_pageerror(self, error) -> None:
        try:
            self._add("page_errors", {"text": str(error)[:MAX_TEXT]})
        except Exception:
            pass

    def _on_request_failed(self, request) -> None:
        try:
            failure = request.failure or ""
            if "ERR_ABORTED" in str(failure):   # our write guard, or a navigation cancelling a load
                return
            if not self.url_allowed(request.url):
                return
            self._add("failed_requests", {"method": request.method, "path": urllib.parse.urlsplit(request.url).path,
                                          "failure": str(failure)[:MAX_TEXT]})
        except Exception:
            pass

    def _on_response(self, response) -> None:
        try:
            if response.status < 500 or response.request.resource_type not in ("document", "xhr", "fetch"):
                return
            if not self.url_allowed(response.url):
                return
            self._add("failed_requests", {"method": response.request.method,
                                          "path": urllib.parse.urlsplit(response.url).path,
                                          "status": response.status})
        except Exception:
            pass

    def snapshot(self, page, url: str, role: str, with_timing: bool = True) -> Dict[str, Any]:
        timing: Optional[Dict[str, Any]] = None
        if with_timing:
            try:
                timing = page.evaluate(TIMING_JS)
            except Exception:
                timing = None
        out = {"url": url, "role": role, **{k: list(v) for k, v in self._buf.items()}, "timing": timing or {}}
        self.begin()
        return out
