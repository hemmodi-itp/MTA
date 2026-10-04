"""
tools.py — tool surface for DiscoveryAgent.

Re-exports the tools/discovery/ pipeline functions so agent.py has a
single, clear import point (mirrors the pattern already established for
ComprehensionAgent's own tools.py).
"""

from tools.discovery.dom_scan import scan_dom, save_dom_scan
from tools.discovery.interactive_dom_scan import promote_checkpoint
from tools.discovery.paths import comprehension_scan_dir
from tools.discovery.synthesize_brd import synthesize_brd_from_dom
from tools.discovery.synthesize_scenarios import (
    synthesize_scenarios_from_dom,
    synthesize_scenarios_from_flows,
)

__all__ = [
    "scan_dom",
    "save_dom_scan",
    "promote_checkpoint",
    "comprehension_scan_dir",
    "synthesize_brd_from_dom",
    "synthesize_scenarios_from_dom",
    "synthesize_scenarios_from_flows",
]
