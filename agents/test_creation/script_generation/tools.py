"""
tools.py — tool surface for ScriptGenerationAgent.

Re-exports update_catalog (tools.catalog.catalog_manager) plus the
locator-map/page-factory/flows-renderer helpers (tools.test_creation.script_generator)
so agent.py has a single, clear import point instead of reaching into three
different tools/ packages directly.
"""

from tools.catalog.catalog_manager import update_catalog
from tools.test_creation.script_generator.build_dom_locator_map import (
    repair_named_locator,
    write_named_locator_map,
    write_pages_module,
)
from tools.test_creation.script_generator.spec_renderer import (
    LOCATOR_FIRST_ACTIONS,
    LOCATOR_OR_NULL_ACTIONS,
    VALUE_REQUIRED_ACTIONS,
    render_flows_module,
    render_spec_from_plan,
)

__all__ = [
    "update_catalog",
    "repair_named_locator",
    "write_named_locator_map",
    "write_pages_module",
    "LOCATOR_FIRST_ACTIONS",
    "LOCATOR_OR_NULL_ACTIONS",
    "VALUE_REQUIRED_ACTIONS",
    "render_flows_module",
    "render_spec_from_plan",
]
