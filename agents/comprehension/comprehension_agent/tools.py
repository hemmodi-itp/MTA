"""
tools.py — tool surface for the ComprehensionAgent.

Re-exports all pipeline tool functions from tools/comprehension/ so that
agent.py has a single, clear import point. In a native Google ADK deployment
these functions would be @tool-decorated and registered with the LlmAgent.
"""

from tools.comprehension.export_scenarios import export_scenarios, load_existing_titles_by_module
from tools.comprehension.extract_requirements import extract_requirements
from tools.comprehension.generate_business_scenarios import generate_business_scenarios
from tools.comprehension.parse_document import parse_all_documents, parse_document
from tools.comprehension.validate_business_scenarios import validate_business_scenarios

__all__ = [
    "parse_document",
    "parse_all_documents",
    "extract_requirements",
    "generate_business_scenarios",
    "validate_business_scenarios",
    "export_scenarios",
    "load_existing_titles_by_module",
]
