import logging
import os
from typing import Optional

from connectors.llm.base import LLMConnector

_log = logging.getLogger("workflow.llm")


class OpenAIConnector(LLMConnector):
    """OpenAI via the openai SDK. Reads OPENAI_API_KEY from env."""

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def generate(self, prompt: str) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            raise ImportError("openai SDK not installed. Run: pip install openai")

        client = OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        if usage:
            _log.info(
                f"[tokens] model={self.model}  "
                f"input={usage.prompt_tokens}  output={usage.completion_tokens}  "
                f"total={usage.total_tokens}"
            )
        return response.choices[0].message.content or ""
