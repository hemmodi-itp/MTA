import logging
import os
from typing import Optional

from connectors.llm.base import LLMConnector

_log = logging.getLogger("workflow.llm")


class ClaudeConnector(LLMConnector):
    """Anthropic Claude via the anthropic SDK. Reads ANTHROPIC_API_KEY from env."""

    DEFAULT_MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 8192

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def generate(self, prompt: str) -> str:
        try:
            import anthropic  # type: ignore
        except ImportError:
            raise ImportError("anthropic SDK not installed. Run: pip install anthropic")

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=self.MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        u = message.usage
        _log.info(
            f"[tokens] model={self.model}  "
            f"input={u.input_tokens}  output={u.output_tokens}  "
            f"total={u.input_tokens + u.output_tokens}"
        )
        return message.content[0].text
