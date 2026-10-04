from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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
