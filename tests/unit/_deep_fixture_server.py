"""Local HTTP server for the Phase 2 deep-discovery browser tests (127.0.0.1 only).

    srv = FixtureServer(routes={"/": handler, ...}, static_dir=FIXTURES)
    srv.start(); srv.url("/widgets.html"); srv.hits["POST /x"]; srv.stop()

A route handler gets (method, path, query, body, headers) and returns (status, headers, body).
Static files are served from tests/fixtures/discovery/ when no route matches.
"""

import http.server
import os
import threading
import urllib.parse
from collections import Counter
from typing import Callable, Dict, Optional, Tuple

FIXTURES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "discovery"))

Handler = Callable[[str, str, Dict[str, list], bytes, Dict[str, str]], Tuple[int, Dict[str, str], bytes]]


class FixtureServer:
    def __init__(self, routes: Optional[Dict[str, Handler]] = None, static_dir: str = FIXTURES):
        self.routes = routes or {}
        self.static_dir = static_dir
        self.hits: Counter = Counter()
        self._srv = None

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self._srv.server_address[1]}{path}"

    def start(self) -> "FixtureServer":
        outer = self

        class _H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _serve(self, method: str):
                parts = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.hits[f"{method} {parts.path}"] += 1
                handler = outer.routes.get(parts.path)
                if handler is None:
                    for prefix, h in outer.routes.items():
                        if prefix.endswith("*") and parts.path.startswith(prefix[:-1]):
                            handler = h
                            break
                if handler is not None:
                    status, headers, payload = handler(method, parts.path, urllib.parse.parse_qs(parts.query), body,
                                                       {k.lower(): v for k, v in self.headers.items()})
                else:
                    fp = os.path.join(outer.static_dir, parts.path.lstrip("/") or "index.html")
                    if os.path.isfile(fp):
                        with open(fp, "rb") as f:
                            status, headers, payload = 200, {"Content-Type": "text/html; charset=utf-8"}, f.read()
                    else:
                        status, headers, payload = 404, {"Content-Type": "text/html"}, b"<h1>Not found</h1>"
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if method != "HEAD":
                    self.wfile.write(payload)

            def do_GET(self):
                self._serve("GET")

            def do_POST(self):
                self._serve("POST")

            def do_DELETE(self):
                self._serve("DELETE")

        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()


def html(body: str, title: str = "Fixture") -> bytes:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{title}</title></head>"
            f"<body>{body}</body></html>").encode("utf-8")
