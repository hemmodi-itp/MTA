"""
extract_requirements — calls the LLM to pull structured data from a Document.

Returns a dict with keys: requirements, business_rules, actors, workflows.
"""

from typing import Any, Dict, List

from tools.shared.llm_response_validator import parse_llm_json
from tools.comprehension.models import (
    Actor,
    BusinessRule,
    Document,
    Requirement,
    TraceabilityReference,
    Workflow,
)
from tools.comprehension.prompts import EXTRACTION_PROMPT, SOURCE_CODE_PROMPT




def _to_traceability(source_dict: Any) -> TraceabilityReference:
    if not isinstance(source_dict, dict):
        return TraceabilityReference()
    return TraceabilityReference(
        source_file=source_dict.get("source_file"),
        page_number=source_dict.get("page_number"),
        section=source_dict.get("section"),
        requirement_id=source_dict.get("requirement_id"),
        jira_story_id=source_dict.get("jira_story_id"),
        confluence_page_id=source_dict.get("confluence_page_id"),
        method_name=source_dict.get("method_name"),
    )


def extract_requirements(document: Document, llm_provider) -> Dict[str, List]:
    """
    Use the LLM to extract requirements, rules, actors, and workflows
    from a single Document.

    Args:
        document:     Parsed Document model.
        llm_provider: Any object with a generate(prompt: str) -> str method.

    Returns:
        {
            "requirements": List[Requirement],
            "business_rules": List[BusinessRule],
            "actors": List[Actor],
            "workflows": List[Workflow],
        }
    """
    if document.source_type == "source_code":
        prompt = SOURCE_CODE_PROMPT.safe_substitute(
            file_name=document.file_name,
            language=document.metadata.get("language", "unknown"),
            content=document.content,
        )
    else:
        prompt = EXTRACTION_PROMPT.safe_substitute(
            content=document.content,
            source_file=document.file_name,
        )

    raw = llm_provider.generate(prompt)
    parsed = parse_llm_json(raw)

    requirements: List[Requirement] = [
        Requirement(
            requirement_id=r.get("requirement_id", f"REQ-{i+1:03d}"),
            description=r.get("description", ""),
            source=_to_traceability(r.get("source")),
        )
        for i, r in enumerate(parsed.get("requirements", []))
    ]

    business_rules: List[BusinessRule] = [
        BusinessRule(
            rule_id=br.get("rule_id", f"BR-{i+1:03d}"),
            description=br.get("description", ""),
            source=br.get("source"),
        )
        for i, br in enumerate(parsed.get("business_rules", []))
    ]

    actors: List[Actor] = [
        Actor(
            name=a.get("name", "Unknown"),
            role=a.get("role"),
        )
        for a in parsed.get("actors", [])
    ]

    workflows: List[Workflow] = [
        Workflow(
            workflow_id=w.get("workflow_id", f"WF-{i+1:03d}"),
            name=w.get("name", ""),
            steps=w.get("steps", []),
        )
        for i, w in enumerate(parsed.get("workflows", []))
    ]

    return {
        "requirements": requirements,
        "business_rules": business_rules,
        "actors": actors,
        "workflows": workflows,
    }
