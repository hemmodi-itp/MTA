import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from connectors.connector_registry import ConnectorRegistry
from connectors.llm.mock import MockLLMConnector
from connectors.llm.bedrock import BedrockConnector
from connectors.llm.claude import ClaudeConnector
from connectors.llm.gemini import GeminiConnector


class ConnectorSelectionTests(unittest.TestCase):
    def _registry(self, llm_mode: str) -> ConnectorRegistry:
        return ConnectorRegistry({"connectors": {"llm": llm_mode}})

    def test_internal_returns_mock(self):
        llm = self._registry("internal").get_llm()
        self.assertIsInstance(llm, MockLLMConnector)

    def test_aws_returns_bedrock(self):
        llm = self._registry("aws").get_llm()
        self.assertIsInstance(llm, BedrockConnector)

    def test_external_returns_claude(self):
        llm = self._registry("external").get_llm()
        self.assertIsInstance(llm, ClaudeConnector)

    def test_gemini_returns_gemini(self):
        llm = self._registry("gemini").get_llm()
        self.assertIsInstance(llm, GeminiConnector)

    def test_explicit_mode_overrides_settings(self):
        registry = self._registry("aws")
        llm = registry.get_llm("internal")
        self.assertIsInstance(llm, MockLLMConnector)

    def test_unknown_mode_raises(self):
        registry = self._registry("internal")
        with self.assertRaises(ValueError):
            registry.get_llm("unknown_mode")

    def test_mock_connector_generate(self):
        llm = self._registry("internal").get_llm()
        result = llm.generate("test prompt")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_default_fallback_to_internal(self):
        registry = ConnectorRegistry({})
        llm = registry.get_llm()
        self.assertIsInstance(llm, MockLLMConnector)


if __name__ == "__main__":
    unittest.main()
