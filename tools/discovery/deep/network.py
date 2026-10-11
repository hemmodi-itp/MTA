"""
network.py — request capture during the crawl and form probes (task 2.5) and the write guard.

NetworkRecorder listens on a role's BrowserContext:
  * keeps `document`, `xhr` and `fetch` requests to allowed hosts (static assets are dropped);
  * tags each with the crawler's current trigger (`navigate <url>`, `expand <name>`,
    `probe <form>:<probe>`) and state;
  * stores NO bodies, header values or cookie values — only header *names*, request field
    names / inferred JSON schemas, content types and status codes.

WriteGuard is a context route: every non-GET/HEAD/OPTIONS request is aborted unless the
crawler explicitly opened a write window (full form probes in a non-prod environment).
Discovery never writes anything else — expander clicks, navigation, prod/unspecified probes.
"""

import json
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.discovery.deep.json_schema import infer, infer_many, merge
from tools.discovery.web.urls import template_path

KEEP_TYPES = ("document", "xhr", "fetch")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
MAX_TRIGGERS = 10
MAX_BODY_SAMPLES = 20
_MULTIPART_NAME = re.compile(r'\bname="([^"]+)"')   # \b: not the filename="..." of a file part


def _kind(resource_type: str, method: str) -> str:
    if resource_type == "document":
        return "page" if method in SAFE_METHODS else "form_submit"
    if resource_type in ("xhr", "fetch"):
        return resource_type
    return "other"


def request_fields(content_type: str, post_data: Optional[str]) -> Tuple[List[str], Optional[Dict[str, Any]]]:
    """(field names, inferred JSON schema) of a request body. Values are discarded."""
    if not post_data:
        return [], None
    ct = (content_type or "").lower()
    if "json" in ct:
        try:
            body = json.loads(post_data)
        except (ValueError, TypeError):
            return [], None
        fields = sorted(body) if isinstance(body, dict) else []
        return fields, infer(body)
    if "x-www-form-urlencoded" in ct:
        return sorted({k for k, _ in urllib.parse.parse_qsl(post_data, keep_blank_values=True)}), None
    if "multipart/form-data" in ct:
        return sorted(set(_MULTIPART_NAME.findall(post_data))), None
    return [], None


class NetworkRecorder:
    def __init__(self, role: str, url_allowed: Callable[[str], bool]):
        self.role = role
        self.url_allowed = url_allowed
        self.trigger = "navigate"
        self.state_id: Optional[str] = None
        self.records: List[Dict[str, Any]] = []
        self._pending_json: List[Tuple[Dict[str, Any], Any]] = []
        self.cookie_hosts: set = set()
        self._probe_log: Optional[List[Dict[str, Any]]] = None

    # ── wiring ──────────────────────────────────────────────────────────
    def attach(self, context) -> None:
        context.on("response", self._on_response)
        context.on("requestfailed", self._on_failed)

    def set_trigger(self, trigger: str, state_id: Optional[str] = None) -> None:
        self.trigger = trigger
        if state_id is not None:
            self.state_id = state_id

    def start_probe_log(self) -> None:
        self._probe_log = []

    def stop_probe_log(self) -> List[Dict[str, Any]]:
        out, self._probe_log = self._probe_log or [], None
        return out

    def refresh_cookies(self, context) -> None:
        try:
            self.cookie_hosts = {c.get("domain", "").lstrip(".") for c in context.cookies()}
        except Exception:
            pass

    # ── capture ─────────────────────────────────────────────────────────
    def _keep(self, request) -> bool:
        if request.resource_type not in KEEP_TYPES:
            return False
        url = request.url
        return url.startswith(("http://", "https://")) and self.url_allowed(url)

    def _base_record(self, request) -> Dict[str, Any]:
        parts = urllib.parse.urlsplit(request.url)
        headers = {k.lower(): v for k, v in (request.headers or {}).items()}
        ct = headers.get("content-type", "")
        try:
            post = request.post_data
        except Exception:
            post = None
        fields, schema = request_fields(ct, post)
        host = parts.hostname or ""
        return {
            "method": request.method, "path_template": template_path(parts.path or "/"),
            "query_params": sorted({k for k, _ in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)}),
            "kind": _kind(request.resource_type, request.method), "host": parts.netloc,
            "auth_header": "authorization" in headers,
            "cookie": host in self.cookie_hosts,
            "request_content_type": ct.split(";")[0].strip() or None,
            "request_fields": fields, "request_schema": schema,
            "trigger": self.trigger, "state_id": self.state_id, "role": self.role,
            "status": None, "aborted": False, "response_content_type": None, "response_schema": None,
        }

    def _on_response(self, response) -> None:
        try:
            request = response.request
            if not self._keep(request):
                return
            rec = self._base_record(request)
            rec["status"] = response.status
            rheaders = {k.lower(): v for k, v in (response.headers or {}).items()}
            rct = (rheaders.get("content-type") or "").split(";")[0].strip()
            rec["response_content_type"] = rct or None
            self.records.append(rec)
            if self._probe_log is not None:
                self._probe_log.append(rec)
            if "json" in rct and rec["kind"] in ("xhr", "fetch"):
                self._pending_json.append((rec, response))
        except Exception:
            pass

    def _on_failed(self, request) -> None:
        # Aborts made by WriteGuard are recorded by add_aborted(); a navigation that cancels an
        # in-flight request is not an endpoint observation.
        return None

    def add_aborted(self, request) -> None:
        try:
            if not self._keep(request):
                return
            rec = self._base_record(request)
            rec["aborted"] = True
            self.records.append(rec)
            if self._probe_log is not None:
                self._probe_log.append(rec)
        except Exception:
            pass

    def drain_json(self) -> None:
        """Read pending JSON response bodies (called from the crawler's own flow, never from a
        Playwright event callback). Only the inferred schema is kept."""
        pending, self._pending_json = self._pending_json, []
        for rec, response in pending:
            try:
                rec["response_schema"] = infer(json.loads(response.body()))
            except Exception:
                continue


class InflightTracker:
    """Counts a context's in-flight requests, so the crawler can wait for a short quiet window
    (QUIET_MS) instead of Playwright's fixed 500 ms `networkidle`."""

    QUIET_MS = 150

    def __init__(self):
        self.inflight = 0

    def attach(self, context) -> None:
        context.on("request", self._up)
        context.on("requestfinished", self._down)
        context.on("requestfailed", self._down)

    def _up(self, _request) -> None:
        self.inflight += 1

    def _down(self, _request) -> None:
        self.inflight = max(0, self.inflight - 1)

    def wait_quiet(self, page, max_ms: int = 5_000) -> bool:
        """True once no request has been in flight for QUIET_MS; False if max_ms passed first."""
        waited = quiet = 0
        step = 50
        while waited < max_ms:
            page.wait_for_timeout(step)      # also pumps Playwright events into the counters
            waited += step
            quiet = quiet + step if self.inflight == 0 else 0
            if quiet >= self.QUIET_MS:
                return True
        return False


class WriteGuard:
    """Context route that aborts writes unless a write window is open."""

    def __init__(self, recorder: Optional[NetworkRecorder] = None):
        self.allow_writes = False
        self.recorder = recorder
        self.aborted = 0

    def install(self, context) -> None:
        context.route("**/*", self._handle)

    def _handle(self, route, request) -> None:
        if request.method.upper() in SAFE_METHODS or self.allow_writes:
            route.continue_()
            return
        self.aborted += 1
        if self.recorder is not None:
            self.recorder.add_aborted(request)
        route.abort()


def aggregate(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Raw request records (all roles) -> api_inventory endpoints, sorted deterministically."""
    groups: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    req_samples: Dict[Tuple[str, str, str], List[Any]] = {}
    for r in records:
        key = (r["method"], r["path_template"], r["kind"])
        g = groups.setdefault(key, {
            "method": r["method"], "path_template": r["path_template"], "kind": r["kind"],
            "statuses": {}, "hosts": set(), "auth": {"authorization_header": False, "cookie": False},
            "request": {"content_type": None, "fields": set(), "query_params": set(), "json_schema": None},
            "response": {"content_type": None, "json_schema": None},
            "triggers": [], "samples": 0, "aborted": 0, "roles": set(),
        })
        g["samples"] += 1
        g["hosts"].add(r["host"])
        g["roles"].add(r["role"])
        g["auth"]["authorization_header"] |= bool(r.get("auth_header"))
        g["auth"]["cookie"] |= bool(r.get("cookie"))
        if r.get("aborted"):
            g["aborted"] += 1
        elif r.get("status") is not None:
            st = str(r["status"])
            g["statuses"][st] = g["statuses"].get(st, 0) + 1
        g["request"]["content_type"] = g["request"]["content_type"] or r.get("request_content_type")
        g["request"]["fields"].update(r.get("request_fields") or [])
        g["request"]["query_params"].update(r.get("query_params") or [])
        if r.get("request_schema") is not None and len(req_samples.setdefault(key, [])) < MAX_BODY_SAMPLES:
            req_samples[key].append(r["request_schema"])
        g["response"]["content_type"] = g["response"]["content_type"] or r.get("response_content_type")
        if r.get("response_schema") is not None:
            g["response"]["json_schema"] = merge(g["response"]["json_schema"], r["response_schema"])
        trig = {"state_id": r.get("state_id"), "action": r.get("trigger"), "role": r.get("role")}
        if trig not in g["triggers"] and len(g["triggers"]) < MAX_TRIGGERS:
            g["triggers"].append(trig)
    out = []
    for key in sorted(groups):
        g = groups[key]
        schemas = req_samples.get(key) or []
        req_schema = None
        for s in schemas:
            req_schema = merge(req_schema, s) if req_schema else s
        out.append({
            "method": g["method"], "path_template": g["path_template"], "kind": g["kind"],
            "statuses": dict(sorted(g["statuses"].items())), "hosts": sorted(g["hosts"]),
            "auth": g["auth"],
            "request": {"content_type": g["request"]["content_type"], "fields": sorted(g["request"]["fields"]),
                        "query_params": sorted(g["request"]["query_params"]), "json_schema": req_schema},
            "response": g["response"], "triggers": g["triggers"], "samples": g["samples"],
            "aborted": g["aborted"], "roles": sorted(g["roles"]),
        })
    return out


__all__ = ["InflightTracker", "NetworkRecorder", "WriteGuard", "aggregate", "request_fields", "infer_many"]
