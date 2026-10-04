"""
prompt.py — LLM prompt templates used by ComprehensionAgent.

The templates themselves live in tools/comprehension/prompts.py, which the
comprehension tools (extract_requirements, generate_business_scenarios) also use;
they are re-exported here so this agent folder keeps its required prompt.py surface.
"""

from tools.comprehension.prompts import (  # noqa: F401
    EXTRACTION_PROMPT,
    SCENARIO_GENERATION_PROMPT,
    SOURCE_CODE_PROMPT,
)

__all__ = ["EXTRACTION_PROMPT", "SOURCE_CODE_PROMPT", "SCENARIO_GENERATION_PROMPT"]
