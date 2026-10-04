"""
engines — deterministic cores of the MTA evaluation pipeline (see the "MTA Redesign" design doc).

Agents under agents/ call these; engines never call an LLM themselves unless their
module docstring says so, and never import from agents/.
"""
