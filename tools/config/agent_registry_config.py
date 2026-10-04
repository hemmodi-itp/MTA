"""
agent_registry_config.py — resolve per-agent fallback policy from
workflows/agent_registry.yaml.

Single point of control for "is the tier-2 Python-deterministic fallback
allowed for agent X" — lets that be turned on/off architecture-wide from one
YAML file instead of editing Python in each agent.
"""

import os
from typing import Optional

import yaml

_DEFAULT_REGISTRY_PATH = os.path.join("workflows", "agent_registry.yaml")


def _load_agents_section(settings: Optional[dict] = None) -> dict:
    settings = settings or {}
    path = (
        settings.get("execution", {}).get("ns", {}).get("agent_registry")
        or _DEFAULT_REGISTRY_PATH
    )
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception:
        return {}
    return raw.get("agents", {}) or {}


def fallback_enabled(agent_key: str, connector_type: str, settings: Optional[dict] = None) -> bool:
    """True only if agent_key declares a `connector_type: <connector_type>` entry
    with `enabled: true` in its `fallbacks:` list in workflows/agent_registry.yaml.
    A missing file, missing agent_key, an empty/absent fallbacks list, a matching
    entry with `enabled` absent/false, or no matching entry at all all resolve to
    False — fail closed, so a broken, absent, or not-yet-configured registry entry
    never silently re-enables a degraded/uncertain result.

    This is the single point of control for every fallback tier across every
    agent (NS reroute, alt-model, Python/rule-based stub, DOM-synthesized
    scenarios, ...) — see workflows/agent_registry.yaml for the full schema."""
    entry = _load_agents_section(settings).get(agent_key, {}) or {}
    fallbacks = entry.get("fallbacks") or []
    return any(
        isinstance(fb, dict) and fb.get("connector_type") == connector_type and fb.get("enabled") is True
        for fb in fallbacks
    )


def python_stub_fallback_enabled(agent_key: str, settings: Optional[dict] = None) -> bool:
    """Back-compat wrapper — existing call sites keep working unchanged."""
    return fallback_enabled(agent_key, "python_stub", settings)
