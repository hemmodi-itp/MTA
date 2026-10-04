"""
http_ssl.py — one shared SSL context for every urllib HTTPS call in the evaluation pipeline.

urllib.request.urlopen() builds a fresh ssl.SSLContext per call when none is given. On some
machines (endpoint security scanning the CA bundle) that takes seconds to minutes per request,
which turned a 114-file repo fetch into an 11-minute step. Building it once per process fixes it.
"""

import ssl
import threading
import urllib.request
from typing import Optional

_ctx: Optional[ssl.SSLContext] = None
_lock = threading.Lock()


def ssl_context() -> ssl.SSLContext:
    global _ctx
    with _lock:
        if _ctx is None:
            _ctx = ssl.create_default_context()
        return _ctx


def urlopen(req, timeout: float = 30):
    """Drop-in for urllib.request.urlopen that reuses the process-wide SSL context."""
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())


class _GuardedRedirects(urllib.request.HTTPRedirectHandler):
    """Re-check every redirect hop against the SSRF policy (tools/agent_eval/net_guard.py)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from tools.agent_eval.net_guard import BlockedTarget, is_allowed_url

        if not is_allowed_url(newurl):
            raise BlockedTarget(f"refused a redirect to a private or internal address ({newurl[:120]})")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_guarded_opener = None


def guarded_urlopen(req, timeout: float = 30):
    """urlopen for user-supplied targets (live apps): the URL and every redirect must be a public host."""
    global _guarded_opener
    from tools.agent_eval.net_guard import BlockedTarget, is_allowed_url

    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    if not is_allowed_url(url):
        raise BlockedTarget(f"refused a request to a private or internal address ({url[:120]})")
    with _lock:
        if _guarded_opener is None:
            _guarded_opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context()),
                                                          _GuardedRedirects())
    return _guarded_opener.open(req, timeout=timeout)
