"""
FailureClassifier — classifies LLM/agent exceptions into routing decisions.

Every LLM-based agent calls BaseAgent.execute_with_fallback() which uses this
classifier to decide whether to retry, reroute, degrade, or fail fast.

Routes:
    RETRY         — same connector, exponential backoff (max 2 attempts)
    NS_HTTP       — reroute via NSHTTPConnector (neuroStack inference)
    ALT_MODEL     — switch to lighter model (haiku) on same connector
    FALLBACK      — deterministic Python in agents/common/fallback_core.py
    HUMAN_REVIEW  — log for human review, then use FALLBACK output (non-blocking)
    FAIL_FAST     — raise immediately; orchestrator marks step as blocking failure
"""

import json


# ── Route constants ────────────────────────────────────────────────────────────
RETRY        = "retry"
NS_HTTP      = "ns_http"
ALT_MODEL    = "alt_model"
FALLBACK     = "fallback"
HUMAN_REVIEW = "human_review"
FAIL_FAST    = "fail_fast"


# ── Exception types recognised by the classifier ──────────────────────────────
class MissingInputError(Exception):
    """Required artifact (dom_elements.json, business_scenarios.json, etc.) not found."""


class LLMTimeoutError(Exception):
    """LLM call timed out."""


class LLMRateLimitError(Exception):
    """LLM provider rate-limited the request."""


class LLMAuthError(Exception):
    """LLM provider rejected credentials."""


class LLMModelUnavailableError(Exception):
    """Requested model is down or unavailable."""


class LLMResponseValidationError(Exception):
    """LLM returned a response that fails schema/JSON validation."""


# ── Classifier ────────────────────────────────────────────────────────────────
def classify(exc: Exception, attempt: int) -> str:
    """
    Return the routing decision for a given exception at a given attempt count.

    Args:
        exc:     The exception raised by the LLM call or agent.
        attempt: How many times this specific operation has already been attempted
                 (0 = first attempt just failed).

    Returns:
        One of the route constants: RETRY, NS_HTTP, ALT_MODEL, FALLBACK,
        HUMAN_REVIEW, or FAIL_FAST.
    """
    # Missing required input — block immediately; no retry makes sense
    if isinstance(exc, MissingInputError):
        return FAIL_FAST

    # Rate limit: retry once with backoff, then reroute to NS
    if isinstance(exc, LLMRateLimitError):
        return RETRY if attempt < 2 else NS_HTTP

    # Timeout: retry once, then reroute
    if isinstance(exc, LLMTimeoutError):
        return RETRY if attempt < 1 else NS_HTTP

    # Auth error: don't retry same connector; go straight to NS
    if isinstance(exc, LLMAuthError):
        return NS_HTTP

    # Model unavailable: try alternate (lighter) model first
    if isinstance(exc, LLMModelUnavailableError):
        return ALT_MODEL

    # Bad JSON / schema validation failure: retry with stricter prompt up to 2x
    if isinstance(exc, (LLMResponseValidationError, json.JSONDecodeError, ValueError)):
        return RETRY if attempt < 2 else FALLBACK

    # Generic connection / unknown error: fallback after first failure
    if isinstance(exc, (ConnectionError, OSError)):
        return RETRY if attempt < 1 else NS_HTTP

    # Unknown exception type → degrade gracefully
    return FALLBACK


def is_llm_error(exc: Exception) -> bool:
    """True if the exception is a known LLM provider error (not a local logic error)."""
    return isinstance(exc, (
        LLMTimeoutError, LLMRateLimitError, LLMAuthError,
        LLMModelUnavailableError, LLMResponseValidationError,
    ))
