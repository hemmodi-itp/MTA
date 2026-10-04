"""
browser.py — one way to start Chromium for every runtime engine (discovery, executor, live client).

    browser = launch_chromium(pw, log)
    ctx = new_context(browser, log, accept_downloads=True, storage_state=...)

  * Sandbox on by default (Playwright's own default is off): the browser visits untrusted sites on the host that holds
    the service's secrets. AQP_CHROMIUM_SANDBOX=0 turns it off; when the platform refuses a sandboxed launch (e.g. a
    container running as root) we fall back to an unsandboxed launch and say so once.
  * Every context gets the SSRF guard (tools/agent_eval/net_guard.install_browser_guard): requests to private,
    loopback, link-local or metadata addresses are aborted, redirects included.
"""

import os
import threading
from typing import Any, Callable, Optional

from tools.agent_eval.net_guard import install_browser_guard

VIEWPORT = {"width": 1366, "height": 900}
_warned = threading.Event()


def _sandbox_wanted() -> bool:
    return os.environ.get("AQP_CHROMIUM_SANDBOX", "1").strip().lower() not in ("0", "false", "no")


def launch_chromium(pw, log: Optional[Callable[..., None]] = None):
    if _sandbox_wanted():
        try:
            return pw.chromium.launch(headless=True, chromium_sandbox=True)
        except Exception as exc:
            if not _warned.is_set():
                _warned.set()
                msg = f"Chromium could not start sandboxed ({type(exc).__name__}); running it without the sandbox."
                if log:
                    try:
                        log(msg, "warning")
                    except TypeError:
                        log(msg)
    return pw.chromium.launch(headless=True)


def new_context(browser, log: Optional[Callable[..., None]] = None, **kwargs: Any):
    kwargs.setdefault("viewport", VIEWPORT)
    if kwargs.get("storage_state") is None:
        kwargs.pop("storage_state", None)
    ctx = browser.new_context(**kwargs)
    install_browser_guard(ctx, log)
    return ctx
