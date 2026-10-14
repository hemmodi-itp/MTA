"""
coverage_server.py — Phase 8.3: run the app under test (an ASGI app) under coverage.py with branch coverage.

    python -m tools.whitebox.coverage_server --app benchmarks.apps.buggy_shop.app:create_app --factory \
        --port 8765 --data-file reports/.coverage --source benchmarks/apps/buggy_shop

Stops on SIGINT / SIGTERM / Windows CTRL_BREAK (AppServer sends it) and saves the coverage data before exiting —
a hard kill would lose it. Only for an app the team runs in a test environment.
"""

from __future__ import annotations

import argparse
import importlib
import signal
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app", required=True, help="module:attribute of the ASGI app (or of its factory)")
    ap.add_argument("--factory", action="store_true", help="the attribute is a factory to call")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--data-file", required=True)
    ap.add_argument("--source", action="append", default=[], help="package / folder to measure (repeatable)")
    args = ap.parse_args(argv)

    import coverage
    cov = coverage.Coverage(data_file=args.data_file, branch=True, source=args.source or None)
    cov.start()
    import uvicorn
    module, _, attr = args.app.partition(":")
    target = getattr(importlib.import_module(module), attr or "app")
    app = target() if args.factory else target
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="warning"))

    def _stop(*_):
        server.should_exit = True
    for sig in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), _stop)
    server.install_signal_handlers = lambda: None      # keep ours
    try:
        server.run()
    finally:
        cov.stop()
        cov.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
