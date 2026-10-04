"""
RuntimeDiscoveryAgent — opens the live deployment and describes what a user can do there.

Deterministic (Playwright + DOM inspection, engines/runtime/discovery.py): crawls the landing
page, same-origin links, routes the app prefetches and page routes known from the repository's
knowledge graph; logs in first when a test account is configured. Produces the runtime profile
(app type, forms, buttons, downloads, chat interface, authentication, pages, API calls, user
flows) that the App Classification and Action Generation engines build on.

The logged-in browser session is handed on as `runtime_session` (a secret the pipeline keeps out of the shared
request and the database) so the Playwright Executor reuses it instead of logging in a second time.
Private / internal targets are refused (tools/agent_eval/net_guard.py).
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.comprehension.runtime_discovery.tools import discover
from tools.agent_eval.net_guard import BlockedTarget
from tools.shared import get_logger


class RuntimeDiscoveryAgent(BaseAgent):
    MODULE_NAME = "runtime_discovery"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.runtime_discovery")

    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        emit = request.get("emit") or (lambda *a, **k: None)
        live_url = (request.get("live_url") or "").strip()
        if request.get("mode") == "brd_only" or not live_url:
            return {"module": self.MODULE_NAME, "status": "skipped", "reason": "not deployed", "runtime_profile": None}

        graph = request.get("repo_graph")
        pages = [n.props.get("path") or n.name for n in graph.of_kind("page")] if graph is not None else []
        routes = [n.name for n in graph.of_kind("route")] if graph is not None else []
        creds = request.get("live_credentials")
        form_pages = _form_pages(graph, request.get("code_chunks") or [])
        emit(f"Inspecting {live_url} in a browser" + (" (logging in with the test account first)" if creds else "")
             + (f"; {len(pages)} page route(s) known from the code." if pages else "."))
        session: Dict[str, Any] = {}
        try:
            profile = discover(live_url, known_pages=pages, known_api_routes=routes, log=emit, credentials=creds,
                               cancel_event=request.get("cancel_event"), session_out=session,
                               known_form_pages=form_pages)
        except BlockedTarget as exc:
            msg = f"The live URL was not opened: {exc}."
            emit(msg, "error")
            return {"module": self.MODULE_NAME, "status": "partial", "error": msg, "runtime_profile": None}
        except Exception as exc:
            emit(f"Runtime discovery failed: {type(exc).__name__}: {exc}", "warning")
            return {"module": self.MODULE_NAME, "status": "partial", "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "runtime_profile": None}

        emit(f"App type: {profile['app_type']} · {profile['forms']} form(s) · {profile['buttons']} button(s) · "
             f"downloads {'yes' if profile['downloads'] else 'no'} · chat {'yes' if profile['chat_interface'] else 'no'} · "
             f"authentication {'yes' if profile['authentication'] else 'no'} ({profile['pages_inspected']} page(s))",
             "success" if profile["app_type"] not in ("Behind login", "Unreachable") else "warning")
        if profile.get("unrendered_form_pages"):
            emit(f"These pages never finished rendering their form for MTA: {', '.join(profile['unrendered_form_pages'][:6])}. "
                 "The live app may still be starting (cold backend) or its API failed; tests that need them cannot run.",
                 "warning")
        login = profile.get("login") or {}
        if login.get("attempted") and not login.get("succeeded"):
            emit(f"Login with the test account failed: {login.get('error')}. Check the email and password on the live app's "
                 "login page.", "warning")
        elif profile.get("needs_credentials"):
            emit("The app is behind a login. Add a test account to the project so MTA can inspect and test it.", "warning")
        out = {"module": self.MODULE_NAME, "status": "success", "runtime_profile": profile}
        if session.get("storage_state"):
            out["runtime_session"] = session["storage_state"]
        return out




_AUTH_PAGE = re.compile(r"/(log-?in|sign-?in|sign-?up|register|auth|forgot|reset)", re.I)


def _form_pages(graph, chunks=()) -> list:
    """Page routes whose code holds an app form (not login / sign-up): the form sits in the page's own file, in a
    file the page links to, or in a component the page's code names (e.g. new/page.tsx renders <RequestForm/>).
    Discovery expects inputs on these pages and looks again if none rendered."""
    if graph is None:
        return []
    try:
        form_files = {f.file_path for f in graph.of_kind("form") if f.file_path}
        components = {Path(f).stem for f in form_files if Path(f).stem.lower() not in ("page", "index", "app")}
        code_by_file: dict = {}
        for c in chunks or []:
            fp = getattr(c, "file_path", None) or (c.get("file_path") if isinstance(c, dict) else None)
            text = getattr(c, "content", None) or (c.get("content") if isinstance(c, dict) else "") or ""
            if fp:
                code_by_file[fp] = code_by_file.get(fp, "") + text
        out = []
        for page in graph.of_kind("page"):
            path = page.props.get("path") or page.name
            if not path or any(ch in path for ch in "[:{") or _AUTH_PAGE.search(path):
                continue
            linked = {graph.nodes[k].file_path for _, k in graph.out(page.key) if k in graph.nodes}
            code = code_by_file.get(page.file_path, "")
            if page.file_path in form_files or linked & form_files or any(re.search(rf"\b{re.escape(n)}\b", code)
                                                                          for n in components):
                out.append(path)
        return out
    except Exception:
        return []
