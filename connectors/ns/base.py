import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict


class NSHTTPConnector:
    """
    HTTP connector for NeuroStack agents.

    Reads agent specs from ns_registry.yaml via ConnectorRegistry.get_ns().
    Each spec declares: method (GET/POST/...), endpoint, timeout.

    Usage:
        ns = ConnectorRegistry(settings).get_ns()
        result = ns.call("comprehension_agent", {"project_name": "demo"})

    Portability: change base_url in settings.yaml to point at a new server.
    Change an endpoint: update ns_registry.yaml only.
    """

    def __init__(self, base_url: str, registry: Dict[str, Any], auth_token: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._registry = registry          # {agent_name: {method, endpoint, timeout, ...}}
        self._auth_token = auth_token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(self, agent_name: str, payload: Dict[str, Any], base_url: str = None) -> Dict[str, Any]:
        """
        Call an NS agent by name. Looks up method + endpoint from the registry,
        makes the HTTP request, and returns the parsed JSON response.

        base_url overrides the connector's default when provided (e.g. per-project URL).

        Raises:
            KeyError if agent_name not found in registry.
            NSCallError on HTTP 4xx/5xx or network failure.
            TimeoutError when the call exceeds the agent's timeout.
        """
        spec = self._registry[agent_name]
        method = spec.get("method", "POST").upper()
        endpoint = spec["endpoint"]
        timeout = float(spec.get("timeout", 30))
        effective_base = (base_url or self._base_url).rstrip("/")

        if method == "GET":
            # Payload becomes query string: /agents/?name=foo
            qs = urllib.parse.urlencode(payload) if payload else ""
            sep = "&" if "?" in endpoint else "?"
            url = effective_base + endpoint + (sep + qs if qs else "")
            body = None
        else:
            url = effective_base + endpoint
            body = json.dumps(payload).encode("utf-8")

        headers = self._build_headers(include_body=body is not None)

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                try:
                    response = json.loads(raw)
                except json.JSONDecodeError:
                    response = {
                        "agent": agent_name,
                        "status": "success",
                        "response": raw.decode("utf-8", errors="replace"),
                    }

                # Validate required output fields declared in the registry spec.
                # If any required field is absent or falsy, raise NSCallError so
                # callers treat this as a failed call and trigger fallbacks.
                required = spec.get("required_output", [])
                missing = [f for f in required if not response.get(f)]
                if missing:
                    raise NSCallError(
                        agent_name, 200,
                        f"response missing required fields {missing} "
                        f"(got keys: {list(response.keys())})"
                    )

                return response

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise NSCallError(agent_name, exc.code, detail) from exc

        except urllib.error.URLError as exc:
            reason = str(exc.reason)
            if "timed out" in reason.lower():
                raise TimeoutError(f"NS call to '{agent_name}' timed out after {timeout}s") from exc
            raise NSCallError(agent_name, None, reason) from exc

    def agents(self) -> list:
        """Return the list of registered agent names."""
        return list(self._registry.keys())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_headers(self, include_body: bool = True) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if include_body:
            headers["Content-Type"] = "application/json"
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers


class NSCallError(Exception):
    """Raised when an NS HTTP call fails."""

    def __init__(self, agent_name: str, status_code: int | None, detail: str) -> None:
        self.agent_name = agent_name
        self.status_code = status_code
        super().__init__(f"[{agent_name}] NS call failed (HTTP {status_code}): {detail}")
