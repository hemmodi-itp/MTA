import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from connectors.adk_model import resolve_adk_model


class ResolveAdkModelTests(unittest.TestCase):
    def test_gemini_returns_bare_model_string(self):
        model = resolve_adk_model({"connectors": {"llm": "gemini"}})
        self.assertEqual(model, "gemini-3.6-flash")

    def test_no_settings_defaults_to_gemini(self):
        model = resolve_adk_model({})
        self.assertEqual(model, "gemini-3.6-flash")

    def test_aws_returns_lite_llm_bedrock_model(self):
        model = resolve_adk_model({"connectors": {"llm": "aws"}})
        self.assertTrue(hasattr(model, "model"))
        self.assertTrue(model.model.startswith("bedrock/"))

    def test_aws_threads_lowercase_env_credentials_into_lite_llm(self):
        # LiteLLM's Bedrock handler needs explicit aws_access_key_id/etc.
        # kwargs — it does not fall back to the lowercase env-var names this
        # repo's .env uses (unlike BedrockConnector, which bridges both
        # cases). resolve_adk_model must bridge them the same way.
        with patch.dict(os.environ, {
            "aws_access_key_id": "FAKEKEY",
            "aws_secret_access_key": "FAKESECRET",
            "aws_session_token": "FAKETOKEN",
        }, clear=False):
            model = resolve_adk_model({"connectors": {"llm": "aws"}})
        self.assertEqual(model._additional_args["aws_access_key_id"], "FAKEKEY")
        self.assertEqual(model._additional_args["aws_secret_access_key"], "FAKESECRET")
        self.assertEqual(model._additional_args["aws_session_token"], "FAKETOKEN")
        self.assertIn("aws_region_name", model._additional_args)

    def test_openai_returns_lite_llm_openai_model(self):
        model = resolve_adk_model({"connectors": {"llm": "openai"}})
        self.assertTrue(model.model.startswith("openai/"))

    def test_ollama_returns_lite_llm_ollama_model(self):
        model = resolve_adk_model({"connectors": {"llm": "ollama"}})
        self.assertTrue(model.model.startswith("ollama/"))

    def test_external_returns_lite_llm_anthropic_model(self):
        model = resolve_adk_model({"connectors": {"llm": "external"}})
        self.assertTrue(model.model.startswith("anthropic/"))

    def test_explicit_model_override_is_honored(self):
        model = resolve_adk_model({
            "connectors": {"llm": "aws"},
            "adk": {"models": {"aws": "bedrock/my-custom-model-id"}},
        })
        self.assertEqual(model.model, "bedrock/my-custom-model-id")

    def test_internal_mode_raises(self):
        with self.assertRaises(ValueError):
            resolve_adk_model({"connectors": {"llm": "internal"}})

    def test_unknown_mode_with_no_override_raises(self):
        with self.assertRaises(ValueError):
            resolve_adk_model({"connectors": {"llm": "not_a_real_provider"}})

    def test_unknown_mode_with_explicit_override_is_honored(self):
        model = resolve_adk_model({
            "connectors": {"llm": "not_a_real_provider"},
            "adk": {"models": {"not_a_real_provider": "openai/custom"}},
        })
        self.assertEqual(model.model, "openai/custom")


if __name__ == "__main__":
    unittest.main()
