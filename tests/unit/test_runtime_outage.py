"""Unit tests for engines/runtime/outage.py and the executor's outage handling (retry decision, shared app health)."""

import http.server
import socket
import threading

import engines.runtime.executor as executor
from engines.runtime.executor import _AppHealth, _retry_reason
from engines.runtime.outage import RATE_LIMITED, SERVER_ERROR, UNREACHABLE, wait_until_up

QUOTA = ("no download was produced — the app showed: “On how to mitigate this issue, please refer to: https://google.github.io/"
         "adk-docs/agents/models/google-gemini/#error-code-429-resource_exhausted 429 RESOURCE_EXHAUSTED. {'error': "
         "{'code': 429, 'message': 'Resource has been exhausted (e.g. check quota).', 'status': 'RESOURCE_EXHAUSTED'}}”")


def test_rate_limited_pattern_and_retry():
    for err in (QUOTA, "HTTP 429 from POST /api/generate", "Rate limit reached for gpt-4o", "Too Many Requests",
                "Quota exceeded for metric generate_content"):
        assert RATE_LIMITED.search(err), err
    for err in ("no download was produced: no download or export control appeared", "Generated 4290 words",
                "Request failed (500)"):
        assert not RATE_LIMITED.search(err), err
    assert _retry_reason({"status": "failed", "error": QUOTA}, 1) == "rate_limited"   # even alone: quota refills


def test_cool_down_pauses_the_next_plan(monkeypatch):
    said = []
    h = _AppHealth("http://127.0.0.1:9/", lambda m, *a: said.append(m))
    h.cool_down(1.5)
    t0 = executor.time.monotonic()
    assert h.wait_up() and executor.time.monotonic() - t0 >= 1.4 and "out of quota" in said[0]
    t1 = executor.time.monotonic()
    assert h.wait_up() and executor.time.monotonic() - t1 < 0.5                     # over: the next plan does not wait


def test_unreachable_and_server_error_patterns():
    for err in ("Error: Page.goto: net::ERR_CONNECTION_TIMED_OUT at https://x/new", "net::ERR_CONNECTION_REFUSED",
                "connect ECONNREFUSED 127.0.0.1:3000", "… the app showed: “Failed to fetch”", "HTTP 502 opening /new"):
        assert UNREACHABLE.search(err), err
    for err in ("net::ERR_ABORTED; maybe frame was detached?", "element not found on /new: button “Go”",
                "HTTP 404 opening /x", "Request failed (500)"):
        assert not UNREACHABLE.search(err), err
    for err in ("the app showed: “Request failed (500)”", "HTTP 500 from POST /api/generate", "Internal Server Error"):
        assert SERVER_ERROR.search(err), err
    for err in ("no download was produced: no download or export control appeared", "Generated 500 words"):
        assert not SERVER_ERROR.search(err), err


def test_retry_reason():
    down = {"status": "failed", "error": "Error: Page.goto: net::ERR_CONNECTION_TIMED_OUT at https://x/"}
    s500 = {"status": "failed", "error": "no download was produced — the app showed: “Request failed (500)”"}
    assert _retry_reason(down, 1) == "unreachable"
    assert _retry_reason(s500, 2) == "server_error" and _retry_reason(s500, 1) == "server_error"  # one more try, alone
    cut = {"status": "failed", "error": "no download was produced", "observations": {"network": [
        {"method": "POST", "path": "/api/generate", "status": 500, "ms": 180234}]}}
    assert _retry_reason(cut, 1) == "server_error"                                  # a 5xx seen only on the wire
    assert _retry_reason({"status": "completed"}, 2) is None
    assert _retry_reason({"status": "failed", "error": "element not found on /new"}, 2) == "locator"  # MTA's miss: one more look
    assert _retry_reason({"status": "failed", "error": "the app rejected the submitted input: “Please add…”"}) is None
    assert executor.RERUNS["server_error"] == 2 and executor.RERUNS["locator"] == 1


def test_cool_down_says_why(monkeypatch):
    said = []
    h = _AppHealth("http://127.0.0.1:9/", lambda m, *a: said.append(m))
    h.cool_down(1.1, "the app keeps answering with server errors")
    assert h.wait_up() and said[0].startswith("The app keeps answering with server errors; pausing")


def _closed_port_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def test_wait_until_up_and_app_health(monkeypatch):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        up = f"http://127.0.0.1:{srv.server_address[1]}/"
        assert wait_until_up(up, 5) is not None
        assert wait_until_up(_closed_port_url(), 0) is None

        said = []
        h = _AppHealth(up, lambda m, *a: said.append(m))
        assert h.wait_up() and not said                      # never marked down: no wait, no message
        h.mark_down(plan_started=1e12)
        assert h.wait_up() and h.outages == [{"recovered_after_s": 0}]
        h.mark_down(plan_started=0.0)                        # failed during the outage already waited out
        assert not h.down

        monkeypatch.setattr(executor, "RECOVERY_WAIT_S", 0)
        dead = _AppHealth(_closed_port_url(), lambda m, *a: said.append(m))
        dead.mark_down(plan_started=1e12)
        assert dead.wait_up() is False and dead.gave_up
        assert dead.wait_up() is False                       # gave up: later plans run without waiting
    finally:
        srv.shutdown()
