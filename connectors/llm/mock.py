from connectors.llm.base import LLMConnector


class MockLLMConnector(LLMConnector):
    """
    Offline stub — returns minimal valid JSON for all prompts.
    Used for internal mode, unit tests, and CI without API keys.
    """

    _EMPTY_RESPONSE = (
        '{"scenario_id": "BS-000", "positive_dataset": [], "negative_variants": []}'
    )

    def generate(self, prompt: str) -> str:  # noqa: ARG002
        return self._EMPTY_RESPONSE
