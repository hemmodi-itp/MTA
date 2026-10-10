"""
Run the Buggy Shop benchmark app locally.

    python -m benchmarks.apps.buggy_shop [--port 8765] [--host 127.0.0.1]

Port defaults to $BENCH_PORT, else 8765. Bugs are toggled with env vars
(BUG_07=1, BUGS=all, BUGS=BUG_01,BUG_07) — see README.md.
"""

import argparse
import os

import uvicorn

from benchmarks.apps.buggy_shop.app import create_app
from benchmarks.apps.buggy_shop.bugs import enabled_bugs


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Buggy Shop benchmark app")
    parser.add_argument("--port", type=int, default=int(os.environ.get("BENCH_PORT", "8765")))
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    bugs = enabled_bugs()
    print(f"Buggy Shop on http://{args.host}:{args.port}  bugs enabled: {', '.join(bugs) or 'none'}")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
