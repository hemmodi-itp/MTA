"""
models.py — schemas of the Phase 1 requirement and traceability artifacts (single source of truth).

  RequirementsDoc        test_comprehension/requirements.json   REQ → atomic AC, quote-verified, classified
  TraceabilityDoc        test_creation/traceability.json        AC ↔ test case ↔ spec/title ↔ latest result
  LlmRequirementsResponse  what the extraction LLM must return (structure strict, enum values coerced later)

contracts/artifacts registers lenient envelopes for the two artifacts; these models are the strict ones the
producers validate against before writing.
"""

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TESTABILITY = ("ui", "api", "non_functional", "manual_only", "not_testable")
PRIORITIES = ("P0", "P1", "P2", "P3")
RISK_TAGS = ("auth", "payment", "data-loss", "PII", "compliance")
# Testability values for which MTA is expected to produce an automated test (the coverage denominator).
AUTOMATABLE = ("ui", "api", "non_functional")

REQ_ID_RE = re.compile(r"^REQ-\d+$")
# AC-03.2 (a criterion) or AC-03.2.1 (an atomic child of a split criterion)
AC_ID_RE = re.compile(r"^AC-\d+\.\d+(\.\d+)?$")

Testability = Literal["ui", "api", "non_functional", "manual_only", "not_testable"]
Priority = Literal["P0", "P1", "P2", "P3"]
RiskTag = Literal["auth", "payment", "data-loss", "PII", "compliance"]
QuoteMatch = Literal["exact", "fuzzy", "none"]
Source = Literal["brd", "dom_inferred"]


class _Model(BaseModel):
    # Producers validate field values strictly; extra keys stay allowed so later phases can add fields
    # without breaking files written by this one.
    model_config = ConfigDict(extra="allow")


# ── requirements.json ────────────────────────────────────────────────────────

class AcceptanceCriterion(_Model):
    id: str
    doc_id: Optional[str] = None             # the id the document itself used, when it had one
    parent_id: Optional[str] = None          # set on an atomic child of a split criterion
    children: List[str] = []                 # set on a non-atomic criterion that was split
    statement: str = Field(min_length=1)
    source: Source = "brd"
    source_quote: Optional[str] = None
    quote_match: QuoteMatch = "none"
    quote_verified: bool = False
    support: float = Field(default=0.0, ge=0.0, le=1.0)
    atomic: bool = True
    atomicity_issues: List[str] = []
    testability: Testability
    testability_reason: str = Field(min_length=1)
    priority: Priority
    priority_source: Literal["brd", "llm", "rule", "default"] = "default"
    risk_tags: List[RiskTag] = []
    classification_source: Literal["llm", "heuristic"] = "heuristic"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("id")
    @classmethod
    def _ac_id(cls, v: str) -> str:
        if not AC_ID_RE.match(v):
            raise ValueError(f"acceptance criterion id {v!r} must look like AC-03.2 or AC-03.2.1")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> "AcceptanceCriterion":
        if self.quote_verified and self.quote_match == "none":
            raise ValueError(f"{self.id}: quote_verified requires quote_match exact|fuzzy")
        if self.parent_id and not self.id.startswith(self.parent_id + "."):
            raise ValueError(f"{self.id}: a child id must extend its parent id {self.parent_id}")
        if any(not c.startswith(self.id + ".") for c in self.children):
            raise ValueError(f"{self.id}: every child id must extend this id")
        return self

    @property
    def is_leaf(self) -> bool:
        return not self.children


class Requirement(_Model):
    id: str
    doc_id: Optional[str] = None
    module_id: Optional[str] = None
    title: str = Field(min_length=1)
    description: str = ""
    source: Source = "brd"
    source_quote: Optional[str] = None
    quote_match: QuoteMatch = "none"
    acceptance_criteria: List[AcceptanceCriterion] = []

    @field_validator("id")
    @classmethod
    def _req_id(cls, v: str) -> str:
        if not REQ_ID_RE.match(v):
            raise ValueError(f"requirement id {v!r} must look like REQ-01 or REQ-001")
        return v


class ModuleStatus(_Model):
    brd_file: Optional[str] = None
    status: Literal["ok", "degraded", "failed"] = "ok"
    limitations: List[str] = []
    extracted_at: Optional[str] = None


class Rejected(_Model):
    module_id: Optional[str] = None
    statement: str
    reason: str


class ReqWarning(_Model):
    id: Optional[str] = None
    module_id: Optional[str] = None
    kind: str
    detail: str = ""


class RequirementsDoc(_Model):
    schema_version: Literal[2] = 2
    artifact: Literal["requirements"] = "requirements"
    project: Optional[str] = None
    updated_at: Optional[str] = None
    modules: Dict[str, ModuleStatus] = {}
    requirements: List[Requirement] = []
    rejected: List[Rejected] = []
    warnings: List[ReqWarning] = []

    @model_validator(mode="after")
    def _unique_ids(self) -> "RequirementsDoc":
        seen_req, seen_ac = set(), set()
        for r in self.requirements:
            if r.id in seen_req:
                raise ValueError(f"duplicate requirement id {r.id}")
            seen_req.add(r.id)
            for ac in r.acceptance_criteria:
                if ac.id in seen_ac:
                    raise ValueError(f"duplicate acceptance criterion id {ac.id}")
                seen_ac.add(ac.id)
        return self

    def criteria(self) -> List[AcceptanceCriterion]:
        return [ac for r in self.requirements for ac in r.acceptance_criteria]

    def leaf_criteria(self, module_id: Optional[str] = None) -> List[AcceptanceCriterion]:
        return [ac for r in self.requirements if module_id is None or r.module_id == module_id
                for ac in r.acceptance_criteria if ac.is_leaf]

    def requirement_of(self) -> Dict[str, Requirement]:
        return {ac.id: r for r in self.requirements for ac in r.acceptance_criteria}


# ── LLM response (structure strict; enum values are coerced by classify.py) ──

class LlmCriterion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = None                 # the document's id when classifying a declared criterion
    statement: str = Field(min_length=1)
    source_quote: Optional[str] = None
    testability: Optional[str] = None
    testability_reason: Optional[str] = None
    priority: Optional[str] = None
    risk_tags: List[str] = []
    split: List[str] = []                    # atomic restatements when the criterion is compound


class LlmRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Optional[str] = None
    title: str = Field(min_length=1)
    description: Optional[str] = ""
    source_quote: Optional[str] = None
    priority: Optional[str] = None
    acceptance_criteria: List[LlmCriterion] = []


class LlmRequirementsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requirements: List[LlmRequirement]


# Gemini structured-output schema for the response above (bounded strings / arrays, as Agent-Eval's schemas).
def _s(n: int) -> Dict[str, Any]:
    return {"type": "string", "maxLength": n}


LLM_RESPONSE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": _s(40), "title": _s(300), "description": _s(2000), "source_quote": _s(600),
                    "priority": {"type": "string", "enum": list(PRIORITIES)},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": _s(40), "statement": _s(1000), "source_quote": _s(600),
                                "testability": {"type": "string", "enum": list(TESTABILITY)},
                                "testability_reason": _s(300),
                                "priority": {"type": "string", "enum": list(PRIORITIES)},
                                "risk_tags": {"type": "array", "maxItems": 5,
                                              "items": {"type": "string", "enum": list(RISK_TAGS)}},
                                "split": {"type": "array", "maxItems": 6, "items": _s(600)},
                            },
                            "required": ["statement", "testability", "testability_reason"],
                        },
                    },
                },
                "required": ["title", "acceptance_criteria"],
            },
        },
    },
    "required": ["requirements"],
}


# ── traceability.json ────────────────────────────────────────────────────────

ResultStatus = Literal["passed", "failed", "flaky", "skipped", "not_run"]   # flaky: Phase 4.7
LinkKind = Literal["direct", "similarity", "inherited", "legacy"]


class LatestResult(_Model):
    status: ResultStatus = "not_run"
    pw_status: Optional[str] = None
    run: Optional[str] = None
    at: Optional[str] = None
    last_failure: Optional[str] = None


class TraceTest(_Model):
    scenario_id: Optional[str] = None
    module_id: Optional[str] = None
    spec_file: Optional[str] = None
    test_title: Optional[str] = None
    type: Optional[str] = None
    ac_ids: List[str] = []
    link: LinkKind = "direct"
    latest_result: LatestResult = LatestResult()
    defect_ids: List[str] = []               # reserved: defects exist from Phase 6 / 11


class UncoveredReason(_Model):
    code: str
    detail: str = ""


class TraceAC(_Model):
    req_id: Optional[str] = None
    module_id: Optional[str] = None
    statement: str = ""
    priority: Optional[Priority] = None
    testability: Optional[Testability] = None
    risk_tags: List[RiskTag] = []
    parent_id: Optional[str] = None
    children: List[str] = []
    tc_ids: List[str] = []
    status: Literal["covered", "partial", "not_covered"] = "not_covered"
    result: Literal["passed", "failed", "flaky", "skipped", "not_run", "mixed"] = "not_run"
    uncovered_reason: Optional[UncoveredReason] = None
    defect_ids: List[str] = []


class TraceabilityDoc(_Model):
    schema_version: Literal[2] = 2
    artifact: Literal["traceability"] = "traceability"
    project: Optional[str] = None
    updated_at: Optional[str] = None
    acs: Dict[str, TraceAC] = {}
    tests: Dict[str, TraceTest] = {}
    unlinked_tests: List[str] = []
    summary: Dict[str, Any] = {}
