"""
models.py — test_cases.json (Phase 3.7) and the schema the test-design LLM response must match.

A test case is a first-class record (plan principle 2): it names the technique that produced it, the ACs it
verifies, its risk and priority, concrete inputs with the rule and source of every value, an outline of steps,
and the oracles a later phase turns into assertions. Strict models: test_cases.json is a new artifact with no v1
variants on disk.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TECHNIQUES = (
    "ep", "bva", "decision_table", "state_transition", "pairwise", "use_case", "crud",
    "error_guessing", "role_matrix", "llm_domain",
)
Technique = Literal[
    "ep", "bva", "decision_table", "state_transition", "pairwise", "use_case", "crud",
    "error_guessing", "role_matrix", "llm_domain",
]
TestType = Literal["positive", "negative", "boundary"]
Priority = Literal["P0", "P1", "P2", "P3"]
Level = Literal["smoke", "standard", "thorough", "exhaustive"]
LEVELS = ("smoke", "standard", "thorough", "exhaustive")
CutReason = Literal["budget", "no_scenario", "duplicate", "profile", "stateful"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Oracle(BaseModel):
    """One expected-outcome check. `type` is open (P5 adds kinds); `source` follows plan 5.2 precedence."""
    model_config = ConfigDict(extra="allow")
    type: str
    source: Optional[str] = None


class Target(Strict):
    """What the case exercises: a form, a page state, a transition or an AC on its own."""
    kind: Literal["form", "state", "transition", "ac", "resource"]
    form_id: Optional[str] = None
    url_template: Optional[str] = None
    sample_url: Optional[str] = None
    field: Optional[str] = None
    to_url_template: Optional[str] = None


class TestCase(Strict):
    __test__ = False
    id: str
    key: str                                    # content key the id is hashed from (stable across runs)
    ac_ids: List[str] = Field(default_factory=list)
    ac_link: Optional[Literal["generator", "token", "llm"]] = None
    scenario_id: Optional[str] = None
    module_id: Optional[str] = None
    title: str
    technique: Technique
    test_type: TestType
    level: Level                                # lowest profile that includes this case
    priority: Priority = "P3"
    risk_score: float = 0.0
    roles: List[str] = Field(default_factory=list)
    preconditions: List[str] = Field(default_factory=list)
    inputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    steps_outline: List[str] = Field(default_factory=list)
    oracles: List[Oracle] = Field(default_factory=list)
    cleanup: List[str] = Field(default_factory=list)
    target: Target
    source: str = "brd"                         # brd | observed | dom | app_map | catalog | llm_inferred, joined by "+"
    confidence: float = 1.0
    est_seconds: int = 10
    tags: List[str] = Field(default_factory=list)
    locator_keys: Dict[str, str] = Field(default_factory=dict)   # field | "submit" -> locator_map.json key
    citations: List[str] = Field(default_factory=list)          # Phase 8.2: file:line of the code rules it rests on


class CutCase(Strict):
    id: str
    title: str
    technique: Technique
    priority: Priority
    risk_score: float
    ac_ids: List[str] = Field(default_factory=list)
    reason: CutReason
    detail: Optional[str] = None


class Conflict(Strict):
    """BRD and observed behaviour disagree — a potential defect for human review (plan 5.2). Never auto-resolved."""
    ac_id: Optional[str] = None
    form_id: str
    field: Optional[str] = None
    probe: str
    brd: str
    observed: str


class DesignBudget(Strict):
    max_tests: int
    max_runtime_minutes: float
    selected: int
    est_runtime_minutes: float
    respected: bool
    p0_over_budget: bool = False


class DesignSummary(Strict):
    generated: int
    selected: int
    cut: int
    by_technique: Dict[str, int] = Field(default_factory=dict)
    by_priority: Dict[str, int] = Field(default_factory=dict)
    by_type: Dict[str, int] = Field(default_factory=dict)
    acs_testable: int = 0
    acs_with_case: int = 0
    ac_coverage_pct: float = 0.0
    acs_without_case: List[str] = Field(default_factory=list)
    testable_ac_ids: List[str] = Field(default_factory=list)
    excluded_by_profile: int = 0          # generated = selected + cut + excluded_by_profile


class LlmStatus(Strict):
    status: Literal["ok", "degraded", "skipped"]
    modules: Dict[str, str] = Field(default_factory=dict)   # module -> ok | degraded:<reason> | skipped
    added: int = 0
    rejected_duplicates: int = 0


class TestCasesDoc(Strict):
    __test__ = False
    schema_version: Literal[2] = 2
    artifact: Literal["test_cases"] = "test_cases"
    project: str
    profile: Level
    content_hash: str                           # hash of the deterministic part (same input → same hash)
    generated_at: Optional[str] = None
    inputs: Dict[str, str] = Field(default_factory=dict)          # artifact -> present | missing
    limitations: List[str] = Field(default_factory=list)
    budget: DesignBudget
    summary: DesignSummary
    llm: LlmStatus
    page_hashes: Dict[str, str] = Field(default_factory=dict)    # url_template -> structural_hash (change fingerprint)
    test_cases: List[TestCase] = Field(default_factory=list)
    cut: List[CutCase] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)


# ── LLM response contract (one call per module) ──────────────────────────────

class DtRule(Strict):
    when: Dict[str, bool]
    then: str


class DecisionTableHint(Strict):
    ac_id: str
    conditions: List[str] = Field(min_length=2, max_length=6)
    actions: List[str] = Field(min_length=1)
    rules: List[DtRule] = Field(min_length=1)


class AcLinkHint(Strict):
    case_id: str
    ac_ids: List[str] = Field(min_length=1)


class ExtraCaseHint(Strict):
    ac_ids: List[str] = Field(min_length=1)
    title: str = Field(min_length=5, max_length=160)
    test_type: TestType
    preconditions: List[str] = Field(default_factory=list)
    steps_outline: List[str] = Field(min_length=1)
    expected: str = Field(min_length=3)
    rationale: str = ""


class NegativePathHint(Strict):
    ac_id: str
    has_negative_path: bool


class DesignHints(Strict):
    decision_tables: List[DecisionTableHint] = Field(default_factory=list)
    ac_links: List[AcLinkHint] = Field(default_factory=list)
    extra_cases: List[ExtraCaseHint] = Field(default_factory=list, max_length=12)
    negative_paths: List[NegativePathHint] = Field(default_factory=list)
