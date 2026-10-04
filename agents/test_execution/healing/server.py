"""
server.py — standalone runner for HealingAgent.

Doubles as the reference example for standalone-running an ADK-based agent in
this codebase (the equivalent of `adk run`/`adk web` for local testing,
without needing the full orchestrator/workflow to invoke it).

    python -m agents.test_execution.healing.server --project AWS_Test
    python -m agents.test_execution.healing.server --project AWS_Test --report path/to/results.json

Requires GOOGLE_API_KEY in the environment (or a .env file) — HealingAgent's
LlmAgent calls Gemini directly via ADK's own model backend.
"""

import argparse
import json
import os
import sys


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _load_settings() -> dict:
    try:
        import yaml
        path = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
            "workflows", "settings.yaml",
        )
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def run(project_name: str, report_json: str = None) -> dict:
    from agents.test_execution.healing.agent import HealingAgent

    settings = _load_settings()
    agent = HealingAgent(settings=settings)
    request = {"project_name": project_name}
    if report_json:
        request["report_json"] = report_json
    return agent.execute(request, {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HealingAgent standalone.")
    parser.add_argument("--project", "-p", required=True, help="Project name (e.g. AWS_Test)")
    parser.add_argument(
        "--report", "-r", default=None,
        help="Path to a specific Playwright JSON report (default: latest on disk)",
    )
    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    os.chdir(project_root)
    _load_env()

    from tools.logger_config import configure_logging
    configure_logging(_load_settings())

    result = run(args.project, report_json=args.report)
    print(json.dumps(result, indent=2))

    if result.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
