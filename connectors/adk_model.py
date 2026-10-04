"""
adk_model.py — resolve the ADK-compatible `model` value for an LlmAgent,
driven by the SAME connectors.llm setting every other agent's
ConnectorRegistry.get_llm() already reads (see workflows/settings.yaml).

ADK's LlmAgent natively supports only Gemini, via a bare model-id string.
Every other provider goes through LiteLLM (`google-adk[extensions]`), whose
model strings are provider-prefixed: "bedrock/...", "anthropic/...",
"openai/...", "ollama/...". workflows/settings.yaml's `adk.models` map holds
the already-prefixed string per provider; _DEFAULT_MODELS below is only the
fallback when a provider has no explicit override configured.
"""

import os
from typing import Any, Dict

_DEFAULT_MODELS: Dict[str, str] = {
    "gemini": "gemini-3.6-flash",
    "aws": "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
    "external": "anthropic/claude-sonnet-4-6",
    "openai": "openai/gpt-4o-mini",
    "ollama": "ollama/llama3",
}


def _bedrock_credential_kwargs() -> Dict[str, str]:
    """LiteLLM's Bedrock handler takes aws_access_key_id/aws_secret_access_key/
    aws_session_token/aws_region_name as explicit kwargs — it does NOT fall
    back to reading the lowercase-named env vars (aws_access_key_id, etc.)
    this repo's .env uses, unlike connectors.llm.bedrock.BedrockConnector,
    which already bridges both cases explicitly. Mirror that same lookup here
    so the ADK path picks up the identical credentials."""
    kwargs = {}
    access_key = os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("aws_access_key_id")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("aws_secret_access_key")
    session_token = os.environ.get("AWS_SESSION_TOKEN") or os.environ.get("aws_session_token")
    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("aws_region") or "us-east-1"
    if access_key:
        kwargs["aws_access_key_id"] = access_key
    if secret_key:
        kwargs["aws_secret_access_key"] = secret_key
    if session_token:
        kwargs["aws_session_token"] = session_token
    kwargs["aws_region_name"] = region
    return kwargs


def resolve_adk_model(settings: dict) -> Any:
    """Return the `model=` value for an ADK LlmAgent.

    Resolved from settings['connectors']['llm'] (the shared connector-mode
    knob) and settings['adk']['models'] (per-mode model-id overrides).
    Raises ValueError/ImportError on misconfiguration — callers should let
    these propagate to whatever already handles ADK-loop failures.
    """
    connector_mode = (settings.get("connectors") or {}).get("llm", "gemini")

    if connector_mode == "internal":
        raise ValueError(
            "connectors.llm is 'internal' (mock) — ADK agents need a real LLM "
            "backend. Set connectors.llm to gemini, aws, external, openai, or ollama."
        )

    model_overrides = (settings.get("adk") or {}).get("models", {})
    model_id = model_overrides.get(connector_mode) or _DEFAULT_MODELS.get(connector_mode)
    if not model_id:
        raise ValueError(
            f"No ADK model configured for connector mode '{connector_mode}'. "
            f"Add one under adk.models.{connector_mode} in workflows/settings.yaml."
        )

    if connector_mode == "gemini":
        return model_id  # ADK's native Gemini support — bare model-id string

    try:
        from google.adk.models.lite_llm import LiteLlm
    except ImportError:
        raise ImportError(
            "LiteLLM support not installed. Run: pip install google-adk[extensions]"
        )

    extra_kwargs = _bedrock_credential_kwargs() if connector_mode == "aws" else {}
    return LiteLlm(model=model_id, **extra_kwargs)
