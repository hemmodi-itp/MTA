"""
live_client.py — talk to a deployed agent so test prompts can be run against it.

Two transports, picked automatically by connect_live_agent():

  HttpAgentClient  — JSON-over-HTTP endpoint (FastAPI/Flask/Express/LangServe/
                     OpenAI-compatible). The endpoint and request shape come from
                     the repo analysis first, then from probing common routes.
  WebChatClient    — browser chat page (Streamlit, Gradio, custom). Driven with
                     Playwright: type the prompt, press Enter, wait for the page
                     text to settle, return what's new.

Every send() returns an AgentResponse; transport failures are reported in it
rather than raised, so one bad test never aborts the whole execution step.
"""

import copy
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.agent_eval.http_ssl import guarded_urlopen as _urlopen

PROBE_MESSAGE = "Hello! In one or two sentences, what can you help me with?"
_PLACEHOLDER = "\u0000AQP_MESSAGE\u0000"

_COMMON_PATHS = [
    "", "/chat", "/api/chat", "/invoke", "/api/invoke", "/query", "/api/query", "/ask", "/api/ask",
    "/agent", "/api/agent", "/run", "/api/run", "/generate", "/api/generate", "/predict", "/message",
    "/api/message", "/chat/invoke", "/v1/chat/completions", "/api/v1/chat",
]
_BODY_TEMPLATES: List[Dict[str, Any]] = [
    {"message": _PLACEHOLDER},
    {"query": _PLACEHOLDER},
    {"input": _PLACEHOLDER},
    {"prompt": _PLACEHOLDER},
    {"question": _PLACEHOLDER},
    {"text": _PLACEHOLDER},
    {"user_input": _PLACEHOLDER},
    {"content": _PLACEHOLDER},
    {"messages": [{"role": "user", "content": _PLACEHOLDER}]},
    {"input": {"input": _PLACEHOLDER}},
    {"model": "default", "messages": [{"role": "user", "content": _PLACEHOLDER}]},
]
_OUTPUT_KEYS = [
    "response", "answer", "output", "result", "reply", "final_answer", "output_text", "generated_text",
    "completion", "text", "content", "message", "data", "choices",
]


@dataclass
class AgentResponse:
    ok: bool
    text: str = ""
    status_code: Optional[int] = None
    latency_ms: int = 0
    error: Optional[str] = None


# ── Response parsing ──────────────────────────────────────────────────────────

def _walk(obj: Any, path: List[str]) -> Any:
    for key in path:
        if isinstance(obj, list):
            obj = obj[int(key)] if key.isdigit() and int(key) < len(obj) else None
        elif isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def extract_text(obj: Any, output_path: Optional[str] = None, _depth: int = 0) -> str:
    """Best-effort: pull the agent's reply text out of an arbitrary JSON body."""
    if output_path:
        found = _walk(obj, output_path.split("."))
        if found is not None:
            return extract_text(found, None, _depth + 1)
    if obj is None or _depth > 6:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        if not obj:
            return ""
        chat = [m for m in obj if isinstance(m, dict) and "content" in m and m.get("role") in ("assistant", "ai", "bot")]
        if chat:
            return extract_text(chat[-1]["content"], None, _depth + 1)
        return extract_text(obj[-1] if isinstance(obj[-1], dict) else obj[0], None, _depth + 1)
    if isinstance(obj, dict):
        if isinstance(obj.get("choices"), list) and obj["choices"]:
            first = obj["choices"][0]
            return extract_text(first.get("message", {}).get("content") or first.get("text"), None, _depth + 1)
        for key in _OUTPUT_KEYS:
            if key in obj and obj[key] not in (None, "", [], {}):
                text = extract_text(obj[key], None, _depth + 1)
                if text:
                    return text
        return json.dumps(obj, ensure_ascii=False)[:4000]
    return str(obj)


def _fill(template: Any, message: str) -> Any:
    if isinstance(template, str):
        return message if template == _PLACEHOLDER else template
    if isinstance(template, list):
        return [_fill(v, message) for v in template]
    if isinstance(template, dict):
        return {k: _fill(v, message) for k, v in template.items()}
    return template


def _placeholder_like(current: Any) -> Any:
    """The message placeholder, shaped like the example value it replaces."""
    if isinstance(current, list):
        if current and isinstance(current[-1], dict):
            last = dict(current[-1])
            key = next((k for k in ("content", "text", "message") if k in last), "content")
            last[key] = _PLACEHOLDER
            last.setdefault("role", "user")
            return [last]
        return [_PLACEHOLDER]
    if isinstance(current, dict):
        key = next((k for k in ("content", "text", "message", "input", "query") if k in current), "content")
        return {**current, key: _PLACEHOLDER}
    return _PLACEHOLDER


def _inject_message(example: Dict[str, Any], dotted: str) -> Dict[str, Any]:
    current = _walk(example, dotted.split("."))
    return _set_path(example, dotted, _placeholder_like(current))


def _set_path(body: Dict[str, Any], dotted: str, value: Any) -> Dict[str, Any]:
    body = copy.deepcopy(body)
    keys = dotted.split(".")
    cursor = body
    for key in keys[:-1]:
        if not isinstance(cursor.get(key), dict):
            cursor[key] = {}
        cursor = cursor[key]
    cursor[keys[-1]] = value
    return body


# ── HTTP transport ────────────────────────────────────────────────────────────

@dataclass
class HttpAgentClient:
    url: str
    body_template: Dict[str, Any]
    method: str = "POST"
    output_path: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: int = 90

    kind = "http"

    def describe(self) -> str:
        shape = json.dumps(_fill(self.body_template, "<prompt>"), ensure_ascii=False)
        return f"{self.method} {self.url} with body {shape}"

    def send(self, message: str) -> AgentResponse:
        status, body_text, latency, error = _http_call(
            self.url, self.method, _fill(self.body_template, message), self.headers, self.timeout
        )
        if error:
            return AgentResponse(ok=False, status_code=status, latency_ms=latency, error=error, text=body_text[:2000])
        text = _parse_body(body_text, self.output_path)
        return AgentResponse(ok=bool(text.strip()), text=text, status_code=status, latency_ms=latency,
                             error=None if text.strip() else "Agent returned an empty response")

    def close(self) -> None:
        pass


def _http_call(url: str, method: str, body: Any, headers: Dict[str, str], timeout: int) -> Tuple[Optional[int], str, int, Optional[str]]:
    data = json.dumps(body).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
                 "User-Agent": "agentic-qa-platform", **headers},
    )
    started = time.monotonic()
    try:
        with _urlopen(req, timeout=timeout) as resp:
            text = resp.read(2_000_000).decode("utf-8", errors="replace")
            return resp.status, text, int((time.monotonic() - started) * 1000), None
    except urllib.error.HTTPError as exc:
        text = exc.read(200_000).decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, text, int((time.monotonic() - started) * 1000), f"HTTP {exc.code}"
    except Exception as exc:  # timeouts, DNS, connection refused, TLS
        reason = getattr(exc, "reason", exc)
        return None, "", int((time.monotonic() - started) * 1000), f"{type(exc).__name__}: {reason}"


def _parse_body(body_text: str, output_path: Optional[str]) -> str:
    stripped = body_text.strip()
    if stripped.startswith("data:"):  # server-sent events: stitch the chunks back together
        chunks = []
        for line in stripped.splitlines():
            if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                payload = line[5:].strip()
                try:
                    chunks.append(extract_text(json.loads(payload), output_path))
                except json.JSONDecodeError:
                    chunks.append(payload)
        return "".join(chunks)
    try:
        return extract_text(json.loads(stripped), output_path)
    except json.JSONDecodeError:
        return stripped


def _missing_fields_from_422(body_text: str) -> List[str]:
    """FastAPI/pydantic validation errors name the body fields they expected."""
    try:
        detail = json.loads(body_text).get("detail")
    except (json.JSONDecodeError, AttributeError):
        return []
    fields = []
    for item in detail if isinstance(detail, list) else []:
        loc = item.get("loc") if isinstance(item, dict) else None
        if isinstance(loc, list) and len(loc) >= 2 and loc[0] == "body":
            fields.append(".".join(str(p) for p in loc[1:]))
    return fields


def _join(base: str, path: str) -> str:
    """base + path, staying on base's origin (paths come from an LLM's reading of the repo)."""
    path = str(path or "")
    if "://" in path or path.startswith("//"):
        path = urllib.parse.urlsplit(path).path or "/"
    return base.rstrip("/") + ("/" + path.lstrip("/") if path else "")


def discover_http_client(live_url: str, interface: Dict[str, Any], log: Callable[[str], None],
                         probe_timeout: int = 45) -> Optional[HttpAgentClient]:
    """Find a working JSON endpoint: repo-declared endpoints first, then common routes."""
    parsed = urllib.parse.urlsplit(live_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    base = live_url.rstrip("/")

    attempts: List[Tuple[str, str, Dict[str, Any], Optional[str]]] = []
    for ep in interface.get("endpoints") or []:
        if not isinstance(ep, dict) or not ep.get("path"):
            continue
        method = str(ep.get("method") or "POST").upper()
        if method not in ("POST", "PUT"):
            continue
        example = ep.get("request_body_example") if isinstance(ep.get("request_body_example"), dict) else {}
        field_name = ep.get("input_field") or "message"
        template = _inject_message(example, str(field_name))
        for root in dict.fromkeys([base, origin]):
            attempts.append((_join(root, str(ep["path"])), method, template, ep.get("output_field")))

    status, _, _, error = _http_call(live_url, "GET", None, {}, probe_timeout)
    if status is None:
        log(f"Live URL is not reachable ({error}).")
        return None

    seen_dead: set = set()
    tried = 0

    def try_one(url: str, method: str, template: Dict[str, Any], output_path: Optional[str]) -> Tuple[Optional[HttpAgentClient], Optional[int], str]:
        nonlocal tried
        tried += 1
        status, text, _, error = _http_call(url, method, _fill(template, PROBE_MESSAGE), {}, probe_timeout)
        if error is None:
            reply = _parse_body(text, output_path)
            if reply.strip() and not reply.lstrip().lower().startswith(("<!doctype", "<html")):
                return HttpAgentClient(url=url, method=method, body_template=template, output_path=output_path), status, text
        return None, status, text

    for url, method, template, output_path in attempts:
        client, _, _ = try_one(url, method, template, output_path)
        if client:
            log(f"Endpoint declared in repo responded: {client.describe()}")
            return client

    for path in _COMMON_PATHS:
        url = _join(base, path)
        if url in seen_dead:
            continue
        client, status, text = try_one(url, "POST", _BODY_TEMPLATES[0], None)
        if client:
            log(f"Found agent endpoint by probing: {client.describe()}")
            return client
        if status in (404, 405, 501) or status is None:
            seen_dead.add(url)
            continue
        # Route exists but rejected the body — learn the field names if the server tells us.
        templates = [{f: _PLACEHOLDER for f in _missing_fields_from_422(text)}] if status == 422 else []
        templates = [t for t in templates if t] + _BODY_TEMPLATES[1:]
        for template in templates:
            if any("." in k for k in template):
                nested: Dict[str, Any] = {}
                for k in template:
                    nested = _set_path(nested, k, _PLACEHOLDER)
                template = nested
            client, _, _ = try_one(url, "POST", template, None)
            if client:
                log(f"Found agent endpoint by probing: {client.describe()}")
                return client
    log(f"No JSON endpoint answered after {tried} probe request(s).")
    return None


# ── Browser chat transport ────────────────────────────────────────────────────

# Only inputs a user can actually type into: read-only/disabled fields (e.g. decorative
# product mock-ups on a marketing page) and search boxes are never a chat box.
_EDITABLE = ":not([readonly]):not([disabled]):not([aria-readonly='true'])"
_INPUT_SELECTORS = [
    'textarea[data-testid="stChatInputTextArea"]',  # Streamlit chat_input
    'textarea[data-testid="textbox"]',               # Gradio
    f"textarea{_EDITABLE}:visible",
    f'input[type="text"]{_EDITABLE}:visible',
    f"input:not([type]){_EDITABLE}:visible",
    '[contenteditable="true"]:visible',
    f'[role="textbox"]{_EDITABLE}:visible',
]


class WebChatClient:
    """Drives a chat web page with Playwright. Not thread-safe — use from one thread."""

    kind = "web_ui"

    def __init__(self, url: str, timeout_s: int = 90, headless: bool = True) -> None:
        from playwright.sync_api import sync_playwright

        self.url = url
        self.timeout_s = timeout_s
        self._pw = sync_playwright().start()
        try:
            from engines.runtime.browser import launch_chromium, new_context
            self._browser = launch_chromium(self._pw)
            self._page = new_context(self._browser).new_page()
        except Exception:
            self._pw.stop()
            raise
        self._selector: Optional[str] = None

    def describe(self) -> str:
        return f"web chat UI at {self.url} (input: {self._selector or 'auto'})"

    def _open(self) -> None:
        page = self._page
        page.goto(self.url, wait_until="domcontentloaded", timeout=60_000)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            for selector in ([self._selector] if self._selector else _INPUT_SELECTORS):
                loc = page.locator(selector).last
                try:
                    if loc.count() and loc.is_visible() and loc.is_editable():
                        self._selector = selector
                        return
                except Exception:
                    continue
            page.wait_for_timeout(1000)  # Streamlit/Gradio render client-side after load
        raise RuntimeError("No chat input box found on the page")

    def _body_text(self) -> str:
        try:
            return self._page.inner_text("body", timeout=10_000)
        except Exception:
            return ""

    def send(self, message: str) -> AgentResponse:
        started = time.monotonic()
        try:
            self._open()  # fresh page per test keeps conversations independent
            before = self._body_text()
            box = self._page.locator(self._selector).last
            try:
                box.click(timeout=5_000)
            except Exception:
                pass  # overlays can intercept the click; fill() focuses the field anyway
            box.fill(message, timeout=10_000)
            box.press("Enter")

            # Wait until the page text stops changing (reply finished streaming).
            last, stable_since = before, time.monotonic()
            deadline = started + self.timeout_s
            changed = False
            while time.monotonic() < deadline:
                self._page.wait_for_timeout(1000)
                now = self._body_text()
                if now != last:
                    last, stable_since, changed = now, time.monotonic(), True
                elif changed and time.monotonic() - stable_since >= 4:
                    break
            reply = _new_text(before, last, message)
            latency = int((time.monotonic() - started) * 1000)
            if not reply:
                return AgentResponse(ok=False, latency_ms=latency, error="No reply appeared on the page before the timeout")
            return AgentResponse(ok=True, text=reply, latency_ms=latency)
        except Exception as exc:
            return AgentResponse(ok=False, latency_ms=int((time.monotonic() - started) * 1000),
                                 error=f"{type(exc).__name__}: {exc}"[:500])

    def close(self) -> None:
        for closer in (self._browser.close, self._pw.stop):
            try:
                closer()
            except Exception:
                pass


_UI_NOISE = {"running...", "running", "stop", "deploy", "send", "submit", "clear", "loading...", "thinking..."}


def _new_text(before: str, after: str, message: str) -> str:
    remaining: Dict[str, int] = {}
    for line in before.splitlines():
        remaining[line.strip()] = remaining.get(line.strip(), 0) + 1
    fresh = []
    for line in after.splitlines():
        key = line.strip()
        if not key:
            continue
        if remaining.get(key):
            remaining[key] -= 1
            continue
        if key == message.strip() or key.lower() in _UI_NOISE:
            continue
        fresh.append(key)
    return "\n".join(fresh).strip()


# ── Auto-detection ────────────────────────────────────────────────────────────

def _looks_like_html(live_url: str) -> bool:
    req = urllib.request.Request(live_url, headers={"User-Agent": "agentic-qa-platform", "Accept": "text/html,*/*"})
    try:
        with _urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "")
            head = resp.read(4096).decode("utf-8", errors="replace").lower()
            return "html" in ctype or "<html" in head
    except Exception:
        return False


class LiveAgentUnreachable(RuntimeError):
    """The live URL doesn't respond (DNS/connection failure, timeout, 5xx) — the deployment is down."""


class NoAgentInterface(RuntimeError):
    """The live URL responds, but nothing on it is a chat box or message API (e.g. a marketing
    site or docs for a desktop/CLI agent) — the agent can't be exercised through this URL."""


def connect_live_agent(live_url: str, interface: Dict[str, Any], log: Callable[[str], None]):
    """Return a connected HttpAgentClient or WebChatClient.

    Raises LiveAgentUnreachable if the URL is down, NoAgentInterface if it is up but offers no
    way to send the agent a message.
    """
    from tools.agent_eval.net_guard import check_target
    check_target(live_url)  # BlockedTarget for private / internal hosts
    status, _, _, error = _http_call(live_url, "GET", None, {}, 30)
    if status is None or status >= 500:
        raise LiveAgentUnreachable(f"The live URL {live_url} is not responding ({error or f'HTTP {status}'}).")

    ui_first = str(interface.get("type", "")).lower() in ("web_chat_ui", "web_ui", "web_form_app", "document_generator",
                                                          "dashboard")
    order = ["web", "http"] if ui_first else ["http", "web"]
    errors = []
    for transport in order:
        if transport == "http":
            client = discover_http_client(live_url, interface, log)
            if client:
                return client
            errors.append("no JSON endpoint answered")
        else:
            if not _looks_like_html(live_url):
                errors.append("live URL does not serve an HTML page")
                continue
            try:
                client = WebChatClient(live_url)
                probe = client.send(PROBE_MESSAGE)
                if probe.ok:
                    log(f"Connected through the {client.describe()}")
                    return client
                client.close()
                errors.append(f"web chat probe failed: {probe.error}")
            except Exception as exc:
                errors.append(f"browser automation failed: {type(exc).__name__}: {exc}")
    raise NoAgentInterface(
        f"{live_url} is up, but it has no chat box or message API MTA could use "
        f"({'; '.join(errors)}). It may be a website or docs page rather than the agent itself."
    )
