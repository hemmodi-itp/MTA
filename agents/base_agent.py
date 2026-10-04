"""
BaseAgent — abstract base class for all agents.

Concrete agents implement `execute(request, state)`. Agents that call an LLM
should use `execute_with_fallback(request, state)` which applies the
three-route failure classifier:

    Tier 0 (primary)     — main LLM connector
    Tier 1 (fallback)    — NSHTTPConnector (neuroStack)
    Tier 2 (last-resort) — Python deterministic fallback in agents/common/fallback_core.py
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from agents.common import failure_classifier as fc
from tools.config.agent_registry_config import fallback_enabled

# Maps a failure_classifier route to the workflows/agent_registry.yaml
# connector_type that gates it. FAIL_FAST/RETRY aren't gated — they never
# leave the primary tier, so there's nothing to enable/disable.
_ROUTE_CONNECTOR_TYPE = {
    fc.NS_HTTP: "ns_http",
    fc.ALT_MODEL: "alt_model",
    fc.FALLBACK: "python_stub",
    fc.HUMAN_REVIEW: "python_stub",
}


class BaseAgent(ABC):
    MODULE_NAME: str = "base"

    @abstractmethod
    def execute(self, request: dict, state: dict) -> Dict[str, Any]:
        raise NotImplementedError

    # ── Failure-classifier execution loop ─────────────────────────────────────

    def _fallback_registry_key(self) -> str:
        """workflows/agent_registry.yaml key for this agent — override via a
        FALLBACK_REGISTRY_KEY class attribute if it differs from MODULE_NAME."""
        return getattr(self, "FALLBACK_REGISTRY_KEY", self.MODULE_NAME)

    def _tier_enabled(self, route: str) -> bool:
        connector_type = _ROUTE_CONNECTOR_TYPE.get(route)
        if connector_type is None:
            return True
        settings = getattr(self, "settings", None)
        return fallback_enabled(self._fallback_registry_key(), connector_type, settings)

    def execute_with_fallback(self, request: dict, state: dict) -> Dict[str, Any]:
        """
        Run with automatic failure routing via FailureClassifier.

        Subclasses should override _run_primary, _run_ns_fallback, and
        _run_py_fallback rather than this method.

        Every non-retry route (NS_HTTP/ALT_MODEL/FALLBACK/HUMAN_REVIEW) is gated
        by workflows/agent_registry.yaml — see tools/config/agent_registry_config.py.
        A disabled tier fails the step immediately (raises) rather than being
        skipped in favor of some other tier further down the chain.
        """
        attempt = 0
        current_connector: Optional[str] = None
        current_model: Optional[str] = None

        while True:
            try:
                if current_connector == "ns_http":
                    result = self._run_ns_fallback(request, state)
                elif current_model is not None:
                    result = self._run_with_alt_model(current_model, request, state)
                else:
                    result = self._run_primary(request, state)

                if attempt > 0:
                    self._log(f"Recovered after {attempt} attempt(s) — "
                              f"connector={current_connector or 'primary'}")
                return result

            except Exception as exc:
                route = fc.classify(exc, attempt)
                self._log(
                    f"attempt={attempt} route={route} exc={type(exc).__name__}: {exc}",
                    level="warning",
                )

                if route == fc.FAIL_FAST:
                    raise

                if route == fc.RETRY:
                    time.sleep(min(2 ** attempt, 30))
                    attempt += 1
                    continue

                if not self._tier_enabled(route):
                    raise RuntimeError(
                        f"{self.__class__.__name__}: primary path failed "
                        f"({type(exc).__name__}: {exc}) and the '{route}' fallback tier "
                        f"is disabled for '{self._fallback_registry_key()}' in "
                        "workflows/agent_registry.yaml — failing rather than degrading"
                    ) from exc

                if route == fc.NS_HTTP:
                    current_connector = "ns_http"
                    attempt += 1
                    continue

                if route == fc.ALT_MODEL:
                    current_model = "claude-haiku-4-5-20251001"
                    attempt += 1
                    continue

                if route in (fc.FALLBACK, fc.HUMAN_REVIEW):
                    if route == fc.HUMAN_REVIEW:
                        self._flag_for_human_review(request, exc)
                    result = self._run_py_fallback(request, state)
                    result["fallback_route"] = route
                    return result

                raise RuntimeError(f"Unhandled route '{route}'") from exc

    # ── Override points ────────────────────────────────────────────────────────

    def _run_primary(self, request: dict, state: dict) -> Dict[str, Any]:
        return self.execute(request, state)

    def _run_ns_fallback(self, request: dict, state: dict) -> Dict[str, Any]:
        raise NotImplementedError("NS fallback not implemented for this agent")

    def _run_with_alt_model(self, model: str, request: dict, state: dict) -> Dict[str, Any]:
        raise NotImplementedError("Alt-model fallback not implemented for this agent")

    def _run_py_fallback(self, request: dict, state: dict) -> Dict[str, Any]:
        return {
            "module": self.MODULE_NAME,
            "status": "degraded",
            "error": "Python fallback not implemented for this agent",
            "fallback_route": fc.FALLBACK,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _flag_for_human_review(self, request: dict, exc: Exception) -> None:
        from tools.state.review_queue import flag_for_human_review
        flag_for_human_review(
            project_name=request.get("project_name", "unknown"),
            agent_name=self.__class__.__name__,
            request=request,
            exc=exc,
        )

    def _log(self, msg: str, level: str = "info") -> None:
        logger = getattr(self, "logger", None)
        if logger:
            log_fn = getattr(logger, level, logger.info)
            log_fn(f"[{self.__class__.__name__}] {msg}")
