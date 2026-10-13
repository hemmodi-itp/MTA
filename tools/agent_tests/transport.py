"""
transport.py — send one conversational turn to the agent under test (Phase 9 conversation transport).

    t = HttpTransport("https://agent.example.com", spec.transport)
    r = t.send(session_id="run1:AT-…:A", message="What are your hours?", history=[])

Unlike tools/agent_eval/live_client.HttpAgentClient (one message, no session), a turn here carries a session id
and — for agents that keep no server-side history — the whole conversation ("{messages}"), and the reply's tool trace
and token usage are read from the paths agent.yaml names.

Safety: HttpTransport goes through tools/agent_eval/http_ssl.guarded_urlopen, so the public-host rule of
tools/agent_eval/net_guard applies to every request and redirect (loopback only with AQP_ALLOW_PRIVATE_TARGETS=1,
the documented local-development switch). AsgiTransport calls an in-process ASGI app (tests, `bench --in-process`)
and never opens a socket.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from tools.agent_eval.http_ssl import guarded_urlopen
from tools.agent_eval.live_client import extract_text


@dataclass
class Reply:
    ok: bool
    text: str = ""
    trace: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    status: Optional[int] = None
    error: Optional[str] = None

    @property
    def tokens(self) -> Optional[float]:
        if not isinstance(self.usage, dict):
            return None
        if isinstance(self.usage.get("total_tokens"), (int, float)):
            return float(self.usage["total_tokens"])
        parts = [self.usage.get(k) for k in ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens")]
        nums = [p for p in parts if isinstance(p, (int, float))]
        return float(sum(nums)) if nums else None


def _walk(obj: Any, dotted: Optional[str]) -> Any:
    if not dotted:
        return None
    for key in dotted.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and key.isdigit() and int(key) < len(obj):
            obj = obj[int(key)]
        else:
            return None
    return obj


def fill_body(template: Any, message: str, session_id: str, history: List[Dict[str, str]]) -> Any:
    """The request body: "{message}" / "{session}" / "{messages}" placeholders replaced, structure kept."""
    if isinstance(template, str):
        if template == "{messages}":
            return [{"role": "assistant" if t["role"] == "bot" else "user", "content": t["text"]} for t in history] + \
                   [{"role": "user", "content": message}]
        if template == "{message}":
            return message
        if template == "{session}":
            return session_id
        return template.replace("{session}", session_id).replace("{message}", message)
    if isinstance(template, list):
        return [fill_body(v, message, session_id, history) for v in template]
    if isinstance(template, dict):
        return {k: fill_body(v, message, session_id, history) for k, v in template.items()}
    return template


def parse(body_text: str, cfg) -> Dict[str, Any]:
    try:
        obj = json.loads(body_text)
    except (json.JSONDecodeError, TypeError):
        return {"text": (body_text or "").strip(), "trace": None, "usage": None}
    trace = _walk(obj, cfg.trace_path)
    usage = _walk(obj, cfg.usage_path)
    return {"text": extract_text(obj, cfg.output_path),
            "trace": trace if isinstance(trace, list) else None,
            "usage": usage if isinstance(usage, dict) else None}


class HttpTransport:
    kind = "http"

    def __init__(self, base_url: str, cfg, opener=guarded_urlopen) -> None:
        self.url = base_url.rstrip("/") + "/" + cfg.path.lstrip("/")
        self.cfg = cfg
        self._open = opener

    def send(self, session_id: str, message: str, history: List[Dict[str, str]]) -> Reply:
        body = json.dumps(fill_body(self.cfg.body, message, session_id, history)).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, method=self.cfg.method, headers={
            "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "mta-agent-tests",
            **self.cfg.headers})
        started = time.perf_counter()
        try:
            with self._open(req, timeout=self.cfg.timeout_s) as resp:
                text = resp.read(2_000_000).decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            return Reply(ok=False, status=exc.code, error=f"HTTP {exc.code}",
                         latency_ms=(time.perf_counter() - started) * 1000)
        except Exception as exc:  # timeouts, refused connections, BlockedTarget on a redirect
            return Reply(ok=False, error=f"{type(exc).__name__}: {exc}"[:300],
                         latency_ms=(time.perf_counter() - started) * 1000)
        latency = (time.perf_counter() - started) * 1000
        p = parse(text, self.cfg)
        return Reply(ok=True, text=p["text"], trace=p["trace"], usage=p["usage"], latency_ms=latency, status=status)


class AsgiTransport:
    """In-process transport for an ASGI app (FastAPI). Used by unit tests and `bench --in-process`."""
    kind = "asgi"

    def __init__(self, app, cfg) -> None:
        from fastapi.testclient import TestClient
        self.client = TestClient(app)
        self.cfg = cfg

    def send(self, session_id: str, message: str, history: List[Dict[str, str]]) -> Reply:
        started = time.perf_counter()
        try:
            r = self.client.request(self.cfg.method, "/" + self.cfg.path.lstrip("/"),
                                    json=fill_body(self.cfg.body, message, session_id, history))
        except Exception as exc:
            return Reply(ok=False, error=f"{type(exc).__name__}: {exc}"[:300],
                         latency_ms=(time.perf_counter() - started) * 1000)
        latency = (time.perf_counter() - started) * 1000
        if r.status_code >= 400:
            return Reply(ok=False, status=r.status_code, error=f"HTTP {r.status_code}", latency_ms=latency)
        p = parse(r.text, self.cfg)
        return Reply(ok=True, text=p["text"], trace=p["trace"], usage=p["usage"], latency_ms=latency,
                     status=r.status_code)
