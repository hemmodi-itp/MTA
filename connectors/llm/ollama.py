import logging
import os
from typing import Optional

from connectors.llm.base import LLMConnector

_log = logging.getLogger("workflow.llm")


class OllamaConnector(LLMConnector):
    """Local Ollama server via its HTTP API. No API key required.

    Reads OLLAMA_BASE_URL from env (default http://localhost:11434).
    """

    DEFAULT_MODEL = "llama3"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")

    def generate(self, prompt: str) -> str:
        import requests

        response = requests.post(
            f"{self._base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        _log.info(f"[tokens] model={self.model}  eval_count={data.get('eval_count', '?')}")
        return data.get("response", "")
