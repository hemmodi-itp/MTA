"""
tools.py — tool surface for LocatorAgent.

Re-exports its two tool dependencies so agent.py has a single, clear import
point. Note these live at the flat tools/ root rather than under a
tools/locator/ subpackage — they're LocatorAgent's only two tool
dependencies, re-exported here anyway for a single clear import point.
"""

from tools.intent_generator import generate_intent_suggestions
from tools.playwright_scanner import PlaywrightScanner

__all__ = [
    "generate_intent_suggestions",
    "PlaywrightScanner",
]
