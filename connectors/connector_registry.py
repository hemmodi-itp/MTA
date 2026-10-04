"""
ConnectorRegistry — central factory for all external connections.

Usage:
    registry = ConnectorRegistry(settings)
    llm = registry.get_llm()          # uses connectors.llm from settings.yaml
    llm = registry.get_llm("gemini")  # explicit override
    ns  = registry.get_ns()           # NSHTTPConnector for NeuroStack agents

Config keys in settings.yaml:
    connectors:
      llm: aws          # aws | external | gemini | internal | openai | ollama
    llm:
      gemini_model: gemini-3.6-flash   # optional; env AQP_GEMINI_MODEL overrides it
    execution:
      ns:
        base_url: "http://localhost:8000"
        auth_token_env: "NS_AUTH_TOKEN"
        registry: "workflows/ns_registry.yaml"
"""

import os
from typing import Dict, Optional

import yaml

from connectors.llm.base import LLMConnector
from connectors.llm.bedrock import BedrockConnector
from connectors.llm.claude import ClaudeConnector
from connectors.llm.gemini import GeminiConnector
from connectors.llm.gemini import configured_model as configured_gemini_model
from connectors.llm.mock import MockLLMConnector
from connectors.llm.ollama import OllamaConnector
from connectors.llm.openai import OpenAIConnector
from connectors.ns.base import NSHTTPConnector

_LLM_MAP = {
    "aws": BedrockConnector,
    "external": ClaudeConnector,
    "gemini": GeminiConnector,
    "internal": MockLLMConnector,
    "openai": OpenAIConnector,
    "ollama": OllamaConnector,
}


class ConnectorRegistry:
    def __init__(self, settings: Optional[Dict] = None) -> None:
        self._settings = settings or {}
        self._connector_cfg = self._settings.get("connectors", {})

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def get_llm(self, mode: Optional[str] = None) -> LLMConnector:
        """
        Return an LLMConnector for the given mode.
        Falls back to connectors.llm in settings, then to 'internal'.
        """
        resolved = mode or self._connector_cfg.get("llm", "internal")
        cls = _LLM_MAP.get(resolved)
        if cls is None:
            raise ValueError(
                f"Unknown LLM connector mode '{resolved}'. "
                f"Choose: {', '.join(_LLM_MAP)}"
            )
        if cls is GeminiConnector:
            # AQP_GEMINI_MODEL > settings llm.gemini_model > workflows/settings.yaml > GeminiConnector.DEFAULT_MODEL
            return cls(model=configured_gemini_model(self._settings))
        return cls()

    # ------------------------------------------------------------------
    # NS  (NeuroStack HTTP)
    # ------------------------------------------------------------------

    def get_ns(self) -> NSHTTPConnector:
        """
        Return an NSHTTPConnector configured from settings.

        Reads execution.ns.base_url, execution.ns.auth_token_env, and
        execution.ns.registry from settings, then loads the agent registry
        YAML to build the connector.
        """
        ns_cfg = self._settings.get("execution", {}).get("ns", {})
        base_url = ns_cfg.get("base_url", "http://localhost:8000")
        auth_token = os.environ.get(ns_cfg.get("auth_token_env", ""), "")
        registry = _load_ns_registry(ns_cfg.get("registry", "workflows/ns_registry.yaml"))
        return NSHTTPConnector(base_url=base_url, registry=registry, auth_token=auth_token)

    # ------------------------------------------------------------------
    # DB
    # ------------------------------------------------------------------

    def get_db(self, mode: Optional[str] = None):
        """Return a DBConnector. Only 'postgres' (DATABASE_URL) is implemented."""
        resolved = mode or self._connector_cfg.get("db", "postgres")
        if resolved != "postgres":
            raise NotImplementedError(f"DB connector '{resolved}' not implemented — use 'postgres'.")
        from connectors.db.postgres import PostgresConnector
        return PostgresConnector()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _load_ns_registry(registry_path: str) -> Dict:
    """Load ns_registry.yaml and return the agents dict."""
    if not registry_path or not os.path.exists(registry_path):
        return {}
    with open(registry_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("agents", {})
