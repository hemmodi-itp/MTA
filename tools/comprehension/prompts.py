"""
prompts.py — LLM prompt templates for BRD/source comprehension
(extract_requirements, generate_business_scenarios).

These live in tools/ (not in the agent folder) because they are shared: the legacy
ComprehensionAgent re-exports them from its prompt.py, and the tools in this package
use them directly — tools must never import from agents/.

Templates use Python's string.Template syntax ($variable).
Call template.safe_substitute(**kwargs) to render.
"""

from string import Template

# ---------------------------------------------------------------------------
# Extraction prompt — for BRD / PRD / user stories / Jira / Confluence exports
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = Template(
    """You are a Business Analyst AI. Your task is to extract structured requirements from the document below.

Document: $source_file
---
$content
---

Extract the following:
1. Requirements — specific functional and non-functional requirements stated in the document.
2. Business rules — constraints, conditions, or validations that must always hold.
3. Actors — users, systems, or roles that interact with the system.
4. Workflows — named sequences of actions from start to a defined end state.

Return ONLY a valid JSON object in this exact structure. No markdown, no explanation.

{
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "description": "Clear, concise requirement statement",
      "source": {
        "source_file": "$source_file",
        "section": "Section heading or null",
        "page_number": null,
        "requirement_id": "Original ID if present, else null",
        "jira_story_id": null
      }
    }
  ],
  "business_rules": [
    {
      "rule_id": "BR-001",
      "description": "Rule statement",
      "source": "Section or method name, or null"
    }
  ],
  "actors": [
    {
      "name": "Actor name",
      "role": "Brief role description"
    }
  ],
  "workflows": [
    {
      "workflow_id": "WF-001",
      "name": "Workflow name",
      "steps": ["Step 1", "Step 2", "Step 3"]
    }
  ]
}

Rules:
- Extract ONLY what is explicitly stated. Do not invent or assume.
- Preserve traceability: always fill source.section when a heading is identifiable.
- Empty lists are valid. Never omit any top-level key.
- Return ONLY the JSON object — no markdown fences, no commentary.
"""
)

# ---------------------------------------------------------------------------
# Source code analysis prompt — for Java / Python / JS / TS files
# ---------------------------------------------------------------------------

SOURCE_CODE_PROMPT = Template(
    """You are a Software Analyst AI. Analyze the source code below and identify the business behaviors it implements.

File: $file_name
Language: $language

Source Code:
---
$content
---

Identify:
1. Features — what business capabilities does this code provide?
2. APIs / operations — what public methods or endpoints are exposed?
3. User actions — what can an end-user trigger through this code?
4. Workflows — what multi-step operation sequences are present?
5. Business rules — what conditions, validations, or constraints are enforced in the code?
6. Actors — who or what interacts with this code?

Return ONLY a valid JSON object in this exact structure. No markdown, no explanation.

{
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "description": "Business capability derived from the code",
      "source": {
        "source_file": "$file_name",
        "method_name": "methodOrFunctionName",
        "section": null,
        "page_number": null,
        "requirement_id": null,
        "jira_story_id": null
      }
    }
  ],
  "business_rules": [
    {
      "rule_id": "BR-001",
      "description": "Rule or validation enforced in code",
      "source": "Class or method name"
    }
  ],
  "actors": [
    {
      "name": "Actor name",
      "role": "Brief description"
    }
  ],
  "workflows": [
    {
      "workflow_id": "WF-001",
      "name": "Workflow name",
      "steps": ["Step 1", "Step 2"]
    }
  ]
}

Rules:
- Only describe behaviors clearly present in the code. No guessing.
- Use method names in source.method_name for traceability.
- Return ONLY the JSON object — no markdown fences, no commentary.
"""
)

# ---------------------------------------------------------------------------
# Scenario generation prompt — combines all extracted data into scenarios
# ---------------------------------------------------------------------------

SCENARIO_GENERATION_PROMPT = Template(
    """You are a Business Analyst AI. Generate Business Scenarios from the extracted requirements below.

Project: $project_name

== Requirements ==
$requirements_json

== Business Rules ==
$business_rules_json

== Actors ==
$actors_json

== Workflows ==
$workflows_json

== Already Covered — do not re-propose these ==
$existing_scenarios_json
(scenarios already generated for this module in a previous run — if the
requirements above still describe one of these, do not emit it again; only
emit scenarios that are genuinely new or not already represented above)

Generate a complete and non-overlapping set of Business Scenarios. Each scenario must:
1. Be directly traceable to one or more requirements above.
2. Cover a single, coherent business goal or user interaction.
3. Include clear preconditions, numbered steps, and an expected result.
4. Reference applicable business rules by their rule_id.
5. Set confidence_score between 0.0 and 1.0 — higher when fully supported by explicit requirements.
6. Not duplicate or trivially reword anything listed in "Already Covered" above.

Return ONLY a valid JSON object in this exact structure. No markdown, no explanation.

{
  "scenarios": [
    {
      "scenario_id": "BS-001",
      "title": "Concise scenario title",
      "business_objective": "What business goal this achieves",
      "actor": "Actor name",
      "preconditions": [
        "Condition that must be true before the scenario starts"
      ],
      "steps": [
        "Step description"
      ],
      "expected_result": "What the system state should be after all steps",
      "business_rules": ["BR-001"],
      "traceability": [
        {
          "source_file": "filename",
          "requirement_id": "REQ-001",
          "section": "Section heading or null",
          "jira_story_id": null,
          "confluence_page_id": null,
          "method_name": null,
          "page_number": null
        }
      ],
      "confidence_score": 0.95
    }
  ]
}

Rules:
- Do not invent scenarios that are not supported by the requirements above.
- Set scenario_id to a placeholder like "BS-001" — it will be replaced with a
  stable, project-wide unique ID before being saved, so numbering does not matter.
- Steps must be action-oriented, written from the actor's perspective.
- Return ONLY the JSON object — no markdown fences, no commentary.
"""
)

__all__ = ["EXTRACTION_PROMPT", "SOURCE_CODE_PROMPT", "SCENARIO_GENERATION_PROMPT"]
