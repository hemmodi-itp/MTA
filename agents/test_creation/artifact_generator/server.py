"""
server.py — standalone runner for the ArtifactGeneratorAgent.

    python -m agents.test_creation.artifact_generator.server --project alterdomus --step intents
    python -m agents.test_creation.artifact_generator.server --project alterdomus --step testcases
    python -m agents.test_creation.artifact_generator.server --project alterdomus --step intents --connector aws
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


def _default_connector_mode(settings: dict) -> str:
    return settings.get("connectors", {}).get("llm", "internal")


def run(project_name: str, step: str = "intents", connector_mode: str = None) -> dict:
    from agents.test_creation.artifact_generator.agent import ArtifactGeneratorAgent

    settings = _load_settings()
    agent = ArtifactGeneratorAgent(mode=step, settings=settings)
    request = {
        "project_name": project_name,
        "connector_mode": connector_mode or _default_connector_mode(settings),
    }
    return agent.execute(request, {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ArtifactGeneratorAgent standalone.")
    parser.add_argument("--project", "-p", required=True, help="Project name (e.g. alterdomus)")
    parser.add_argument(
        "--step", "-s",
        default="intents",
        choices=["intents", "testcases"],
        help="Which pass to run (default: intents)",
    )
    parser.add_argument(
        "--connector",
        default=None,
        choices=["aws", "external", "gemini", "internal"],
        help="LLM connector (default: from workflows/settings.yaml)",
    )
    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    os.chdir(project_root)
    _load_env()

    from tools.logger_config import configure_logging
    configure_logging(_load_settings())

    result = run(args.project, step=args.step, connector_mode=args.connector)
    print(json.dumps(result, indent=2))

    if result.get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
