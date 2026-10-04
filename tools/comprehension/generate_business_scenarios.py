"""
generate_business_scenarios — calls the LLM to produce Business Scenarios
from the extracted requirements, rules, actors, and workflows.
"""

import json
from typing import Any, Dict, List, Optional

from tools.shared.llm_response_validator import parse_llm_json
from tools.comprehension.models import (
    Actor,
    BusinessRule,
    BusinessScenario,
    Requirement,
    TraceabilityReference,
    Workflow,
)
from tools.comprehension.prompts import SCENARIO_GENERATION_PROMPT
from tools.state.artifact_registry import ArtifactRegistry




def _to_traceability_list(trace_list: Any) -> List[TraceabilityReference]:
    if not isinstance(trace_list, list):
        return []
    refs = []
    for t in trace_list:
        if not isinstance(t, dict):
            continue
        refs.append(
            TraceabilityReference(
                source_file=t.get("source_file"),
                page_number=t.get("page_number"),
                section=t.get("section"),
                requirement_id=t.get("requirement_id"),
                jira_story_id=t.get("jira_story_id"),
                confluence_page_id=t.get("confluence_page_id"),
                method_name=t.get("method_name"),
            )
        )
    return refs


def generate_business_scenarios(
    project_name: str,
    requirements: List[Requirement],
    business_rules: List[BusinessRule],
    actors: List[Actor],
    workflows: List[Workflow],
    llm_provider,
    module_id: Optional[str] = None,
    module_name: Optional[str] = None,
    registry: Optional[ArtifactRegistry] = None,
    existing_scenarios: Optional[List[dict]] = None,
) -> List[BusinessScenario]:
    """
    Use the LLM to generate Business Scenarios from extracted data.

    Args:
        project_name:   Display name used in the prompt context.
        requirements:   Extracted Requirement objects.
        business_rules: Extracted BusinessRule objects.
        actors:         Extracted Actor objects.
        workflows:      Extracted Workflow objects.
        llm_provider:   Any object with generate(prompt: str) -> str.
        registry:       When provided, scenario_id is assigned from the
                        registry (module-prefixed, content-signature-deduped)
                        instead of the LLM's own numbering — this is what
                        keeps re-runs and new modules from colliding with
                        IDs already used by other modules/runs.
        existing_scenarios: [{"scenario_id": ..., "title": ...}, ...] already
                        generated for this module in a prior run — passed
                        into the prompt so the LLM steers away from
                        re-proposing scenarios that already exist.

    Returns:
        List of BusinessScenario objects.
    """
    prompt = SCENARIO_GENERATION_PROMPT.safe_substitute(
        project_name=project_name,
        requirements_json=json.dumps(
            [r.model_dump() for r in requirements], indent=2
        ),
        business_rules_json=json.dumps(
            [br.model_dump() for br in business_rules], indent=2
        ),
        actors_json=json.dumps(
            [a.model_dump() for a in actors], indent=2
        ),
        workflows_json=json.dumps(
            [w.model_dump() for w in workflows], indent=2
        ),
        existing_scenarios_json=json.dumps(existing_scenarios or [], indent=2),
    )

    raw = llm_provider.generate(prompt)
    parsed = parse_llm_json(raw)

    scenarios: List[BusinessScenario] = []
    for i, s in enumerate(parsed.get("scenarios", [])):
        title = s.get("title", "")
        business_objective = s.get("business_objective", "")
        steps = s.get("steps", [])
        expected_result = s.get("expected_result", "")

        content_hash = None
        if registry is not None:
            scenario_id, _is_new, content_hash = registry.get_or_create_id(
                module_id,
                "BS",
                title,
                business_objective,
                "|".join(steps),
                expected_result,
            )
        else:
            scenario_id = s.get("scenario_id", f"BS-{i+1:03d}")

        scenarios.append(
            BusinessScenario(
                scenario_id=scenario_id,
                title=title,
                business_objective=business_objective,
                actor=s.get("actor", ""),
                preconditions=s.get("preconditions", []),
                steps=steps,
                expected_result=expected_result,
                business_rules=s.get("business_rules", []),
                traceability=_to_traceability_list(s.get("traceability", [])),
                confidence_score=float(s.get("confidence_score", 0.0)),
                module_id=module_id,
                module_name=module_name,
                content_hash=content_hash,
            )
        )
    return scenarios
