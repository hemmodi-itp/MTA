from typing import Any, Dict, List, Optional

from pydantic import BaseModel, model_serializer


class TraceabilityReference(BaseModel):
    source_file: Optional[str] = None
    page_number: Optional[int] = None
    section: Optional[str] = None
    requirement_id: Optional[str] = None
    jira_story_id: Optional[str] = None
    confluence_page_id: Optional[str] = None
    method_name: Optional[str] = None


class Document(BaseModel):
    file_name: str
    file_type: str
    source_type: str
    content: str
    metadata: Dict[str, Any] = {}


class Requirement(BaseModel):
    requirement_id: str
    description: str
    source: Optional[TraceabilityReference] = None


class BusinessRule(BaseModel):
    rule_id: str
    description: str
    source: Optional[str] = None


class Actor(BaseModel):
    name: str
    role: Optional[str] = None


class Workflow(BaseModel):
    workflow_id: str
    name: str
    steps: List[str]


class BusinessScenario(BaseModel):
    scenario_id: str
    title: str
    business_objective: str
    actor: str
    preconditions: List[str]
    steps: List[str]
    expected_result: str
    business_rules: List[str] = []
    traceability: List[TraceabilityReference] = []
    confidence_score: float = 0.0
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    content_hash: Optional[str] = None
    # Phase 1: acceptance criteria this scenario covers (requirements.json ids) and how the link was made
    # ("llm" | "similarity"). Serialised only when set, so projects without requirements are unchanged.
    ac_ids: List[str] = []
    ac_link_source: Optional[str] = None

    @model_serializer(mode="wrap")
    def _omit_empty_ac_links(self, handler):
        data = handler(self)
        if not data.get("ac_ids"):
            data.pop("ac_ids", None)
            data.pop("ac_link_source", None)
        elif data.get("ac_link_source") is None:
            data.pop("ac_link_source", None)
        return data
