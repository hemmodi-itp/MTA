"""
Regression: tools/agent_eval/http_ssl.guarded_urlopen deadlocked on its first call in a process (it held the module's
non-reentrant lock while ssl_context() took it again). Found by the Phase 9 buggy_bot benchmark; it also blocked the
HTTP path of live_agent_execution. The call runs in a worker thread so a regression fails fast instead of hanging.
"""

import http.server
import threading
import urllib.request

import pytest

from tools.agent_eval import http_ssl
from tools.agent_eval.net_guard import BlockedTarget

pytestmark = pytest.mark.mta


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


def test_first_guarded_call_does_not_deadlock(server, monkeypatch):
    monkeypatch.setenv("AQP_ALLOW_PRIVATE_TARGETS", "1")
    monkeypatch.setattr(http_ssl, "_guarded_opener", None)  # the first-call path
    out = {}

    def call():
        with http_ssl.guarded_urlopen(urllib.request.Request(server), timeout=5) as r:
            out["body"] = r.read()

    t = threading.Thread(target=call, daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "guarded_urlopen deadlocked"
    assert out["body"] == b"ok"


def test_guard_still_refuses_private_targets(server, monkeypatch):
    monkeypatch.delenv("AQP_ALLOW_PRIVATE_TARGETS", raising=False)
    with pytest.raises(BlockedTarget):
        http_ssl.guarded_urlopen(urllib.request.Request(server), timeout=5)
