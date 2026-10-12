"""tools.py — tool surface for TestDesignAgent (re-exported from the shared core, tools/test_design/)."""

from tools.test_design.design import design, generate_all
from tools.test_design.inputs import DesignInputs
from tools.test_design.locators import merge_form_locators, update_locator_map_file
from tools.test_design.store import cases_by_scenario, load_doc, write_doc

__all__ = [
    "DesignInputs", "cases_by_scenario", "design", "generate_all", "load_doc", "merge_form_locators",
    "update_locator_map_file", "write_doc",
]
