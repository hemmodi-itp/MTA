from abc import ABC, abstractmethod


class LLMConnector(ABC):
    """
    Minimal LLM interface.  All agents depend only on this —
    never on a concrete SDK or cloud vendor.
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send a prompt and return the raw text response."""
        raise NotImplementedError


# ── errors a connector may raise (vendor-neutral, so callers can tell them apart) ──
# None of them subclasses ValueError: tools/agent_eval/llm_json.generate_json retries only on
# ValueError (a parse failure), and re-sending the identical prompt can't fix any of these.

class LLMError(RuntimeError):
    """Base class for connector-level LLM failures."""


class LLMTimeoutError(LLMError, TimeoutError):
    """The call exceeded its deadline (connection, read, or overall streaming deadline)."""


class LLMTruncatedError(LLMError):
    """The model stopped at its output-token limit (finish_reason MAX_TOKENS): the reply is incomplete."""


class LLMBlockedError(LLMError):
    """The prompt or the reply was blocked by the provider's safety / content filters."""
