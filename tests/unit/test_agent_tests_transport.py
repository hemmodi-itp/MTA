"""Conversation transport (tools/agent_tests/transport.py): body filling, reply parsing, the net_guard rule."""

import io
import json

import pytest

from tools.agent_tests.spec import TransportCfg
from tools.agent_tests.transport import AsgiTransport, HttpTransport, Reply, fill_body, parse

pytestmark = pytest.mark.mta

SERVER = TransportCfg(path="/chat", body={"session_id": "{session}", "message": "{message}"}, output_path="reply",
                      trace_path="trace", usage_path="usage", history="server")
CLIENT = TransportCfg(path="/v1/chat", body={"model": "x", "messages": "{messages}"}, history="client")


def test_fill_body_server_and_client_history():
    assert fill_body(SERVER.body, "hi", "s1", []) == {"session_id": "s1", "message": "hi"}
    hist = [{"role": "user", "text": "a"}, {"role": "bot", "text": "b"}]
    assert fill_body(CLIENT.body, "c", "s1", hist) == {"model": "x", "messages": [
        {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]}
    assert fill_body({"q": "Q: {message} ({session})"}, "hi", "s9", []) == {"q": "Q: hi (s9)"}


def test_spec_rejects_inconsistent_history_and_foreign_paths():
    with pytest.raises(Exception, match="session"):
        TransportCfg(history="server", body={"message": "{message}"})
    with pytest.raises(Exception, match="messages"):
        TransportCfg(history="client", body={"message": "{message}"})
    with pytest.raises(Exception, match="own origin"):
        TransportCfg(history="none", path="https://evil.example/chat")


def test_parse_reply_trace_usage():
    p = parse(json.dumps({"reply": "Open 9-6", "trace": [{"tool": "kb_search"}], "usage": {"input_tokens": 3}}), SERVER)
    assert p == {"text": "Open 9-6", "trace": [{"tool": "kb_search"}], "usage": {"input_tokens": 3}}
    assert parse("plain text", SERVER)["text"] == "plain text"
    assert Reply(ok=True, usage={"input_tokens": 3, "output_tokens": 4}).tokens == 7
    assert Reply(ok=True, usage={"total_tokens": 9}).tokens == 9 and Reply(ok=True).tokens is None


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_transport_uses_the_injected_guarded_opener():
    seen = {}

    def opener(req, timeout):
        seen.update(url=req.full_url, body=json.loads(req.data), timeout=timeout)
        return _Resp(json.dumps({"reply": "ok", "trace": []}).encode())

    r = HttpTransport("https://agent.example.com/", SERVER, opener=opener).send("s1", "hello", [])
    assert r.ok and r.text == "ok" and r.trace == [] and r.status == 200
    assert seen == {"url": "https://agent.example.com/chat", "body": {"session_id": "s1", "message": "hello"},
                    "timeout": SERVER.timeout_s}


def test_http_transport_refuses_private_targets_by_default(monkeypatch):
    monkeypatch.delenv("AQP_ALLOW_PRIVATE_TARGETS", raising=False)
    r = HttpTransport("http://127.0.0.1:9", SERVER).send("s1", "hello", [])
    assert not r.ok and "BlockedTarget" in r.error  # net_guard refused before any socket was opened


def test_asgi_transport_round_trip():
    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/chat")
    def chat(body: dict):
        return {"reply": f"echo {body['message']} @ {body['session_id']}", "usage": {"total_tokens": 5}}

    r = AsgiTransport(app, SERVER).send("s7", "hi", [])
    assert r.ok and r.text == "echo hi @ s7" and r.tokens == 5 and r.trace is None
    assert not AsgiTransport(app, TransportCfg(path="/missing", history="none")).send("s", "x", []).ok
