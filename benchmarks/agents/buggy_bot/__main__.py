"""
Run the Buggy Bot benchmark chatbot locally.

    python -m benchmarks.agents.buggy_bot [--port 8766] [--host 127.0.0.1]

Port defaults to $BOT_PORT, else 8766. Weaknesses are toggled with env vars
(BOT_BUG_01=1, BOT_BUGS=all) — see README.md.
"""

import argparse
import os

import uvicorn

from benchmarks.agents.buggy_bot.app import create_app, enabled_weaknesses


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Buggy Bot benchmark chatbot")
    parser.add_argument("--port", type=int, default=int(os.environ.get("BOT_PORT", "8766")))
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    weak = enabled_weaknesses()
    print(f"Buggy Bot on http://{args.host}:{args.port}  weaknesses enabled: {', '.join(weak) or 'none'}")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
