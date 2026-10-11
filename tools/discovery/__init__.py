"""tools.discovery — DOM scan, synthesis and (Phase 2) deep discovery.

Exports are resolved lazily (PEP 562): importing a light submodule such as
tools.discovery.web (shared with the Agent-Eval runtime engine) must not drag in
the Playwright scanner and the legacy intent stack.
"""

import importlib

_EXPORTS = {
    "DiscoveryResult": "tools.discovery.models",
    "DomIntent": "tools.discovery.models",
    "scan_dom": "tools.discovery.dom_scan",
    "save_dom_scan": "tools.discovery.dom_scan",
    "synthesize_brd_from_dom": "tools.discovery.synthesize_brd",
    "synthesize_scenarios_from_dom": "tools.discovery.synthesize_scenarios",
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'tools.discovery' has no attribute '{name}'")
    return getattr(importlib.import_module(module), name)
