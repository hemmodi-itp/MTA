"""
models.py — Pydantic v2 contracts for MTA's pipeline artifacts (schema_version 2).

Lenient by design (extra="allow"): v1 artifacts on disk vary across projects and
generations (see docs/audit/current_state.md §8), and every existing project must
keep validating. Each model requires only what downstream code actually indexes,
and types the structure (lists are lists, maps are maps, ids are strings).

Envelope rules (docs/phases/phase-0-design.md §7.2):
  * dict artifacts (dom_elements, business_scenarios, test_suite, execution_results)
    carry `schema_version` + `artifact` next to their v1 keys;
  * list/map artifacts move their v1 body under one key:
      test_data -> "datasets", scenario_element_map -> "scenarios", test_plans -> "plans".
  * locator_map.json is read by the TS runtime and keeps its v1 shape (validated only).
  * requirements / traceability (Phase 1) are new dict artifacts, strict (see the bottom of this file).
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 2


class Lenient(BaseModel):
    model_config = ConfigDict(extra="allow")


# ── dom_elements.json ────────────────────────────────────────────────────────

class DomElement(Lenient):
    locator_id: Optional[str] = None
    tag: Optional[str] = None
    display_text: Optional[str] = None
    semantic_locators: Optional[Dict[str, Any]] = None
    attribute_locators: Optional[Dict[str, Any]] = None
    recommended_locator: Optional[Dict[str, Any]] = None
    locator_candidates: Optional[List[Any]] = None
    quality: Optional[Dict[str, Any]] = None
    # Phase 2 deep capture (discovery.deep) — optional, absent on legacy scans
    capture_mode: Optional[str] = None
    capture_reason: Optional[str] = None
    constraints: Optional[Dict[str, Any]] = None
    containers: Optional[List[Dict[str, Any]]] = None
    frame: Optional[Dict[str, Any]] = None


class DomPage(Lenient):
    page_id: Optional[str] = None
    url: Optional[str] = None
    elements: List[DomElement] = Field(default_factory=list)


class DomElementsV2(Lenient):
    schema_version: Literal[2] = 2
    artifact: Literal["dom_elements"] = "dom_elements"
    url: Optional[str] = None
    project: Optional[str] = None
    elements: List[DomElement] = Field(default_factory=list)
    pages: Optional[List[DomPage]] = None
    scan: Optional[Dict[str, Any]] = None          # Phase 2 deep-scan stats


# ── business_scenarios.json ──────────────────────────────────────────────────

class Scenario(Lenient):
    scenario_id: str
    title: Optional[str] = None
    steps: List[Any] = Field(default_factory=list)
    module_id: Optional[str] = None


class BusinessScenariosV2(Lenient):
    schema_version: Literal[2] = 2
    artifact: Literal["business_scenarios"] = "business_scenarios"
    project: Optional[str] = None
    total_scenarios: Optional[int] = None
    scenarios: List[Scenario] = Field(default_factory=list)
    modules: Optional[Any] = None


# ── test_data.json ───────────────────────────────────────────────────────────

class DataField(Lenient):
    field_name: Optional[str] = None
    field_type: Optional[str] = None
    value: Any = None


class DataIteration(Lenient):
    fields: List[DataField] = Field(default_factory=list)
    expected_error: Optional[str] = None


class NegativeVariant(Lenient):
    variant_id: Optional[str] = None
    variant_type: Optional[str] = None
    description: Optional[str] = None
    iterations: List[DataIteration] = Field(default_factory=list)


class ScenarioDataset(Lenient):
    scenario_id: str
    testdata_id: Optional[str] = None
    scenario_title: Optional[str] = None
    positive_dataset: List[DataField] = Field(default_factory=list)
    negative_variants: List[NegativeVariant] = Field(default_factory=list)


class TestDataV2(Lenient):
    __test__ = False  # not a pytest test class
    schema_version: Literal[2] = 2
    artifact: Literal["test_data"] = "test_data"
    datasets: List[ScenarioDataset] = Field(default_factory=list)


# ── scenario_element_map.json ────────────────────────────────────────────────

class MappedElement(Lenient):
    locator_id: Optional[str] = None
    playwright_expr: Optional[str] = None
    cluster: Optional[str] = None
    confidence: Optional[float] = None


class ScenarioMapEntry(Lenient):
    scenario_title: Optional[str] = None
    relevant_elements: List[MappedElement] = Field(default_factory=list)


class ScenarioElementMapV2(Lenient):
    schema_version: Literal[2] = 2
    artifact: Literal["scenario_element_map"] = "scenario_element_map"
    scenarios: Dict[str, ScenarioMapEntry] = Field(default_factory=dict)


# ── test_plans.json ──────────────────────────────────────────────────────────

class PlanStep(Lenient):
    action: str
    locator_key: Optional[str] = None
    value: Any = None
    message: Optional[str] = None


class PlanTest(Lenient):
    __test__ = False
    name: str
    type: Optional[str] = None
    steps: List[PlanStep] = Field(default_factory=list)


class TestPlan(Lenient):
    __test__ = False
    tests: List[PlanTest] = Field(default_factory=list)
    missing_actions: List[Any] = Field(default_factory=list)
    missing_locators: List[Any] = Field(default_factory=list)
    dropped_for_safety: List[Dict[str, Any]] = Field(default_factory=list)


class TestPlansV2(Lenient):
    __test__ = False
    schema_version: Literal[2] = 2
    artifact: Literal["test_plans"] = "test_plans"
    plans: Dict[str, TestPlan] = Field(default_factory=dict)


# ── test_suite.json ──────────────────────────────────────────────────────────

class SuiteSpec(Lenient):
    spec_id: str
    file: Optional[str] = None
    module_id: Optional[str] = None
    status: Optional[str] = None
    tier_used: Optional[int] = None
    generation_mode: Optional[str] = None


class TestSuiteV2(Lenient):
    __test__ = False
    schema_version: Literal[2] = 2
    artifact: Literal["test_suite"] = "test_suite"
    project: Optional[str] = None
    specs: List[SuiteSpec] = Field(default_factory=list)
    updated_at: Optional[str] = None
    total_scenarios: Optional[int] = None
    new_additions: Optional[Any] = None


# ── execution results (MTA-normalised run record) ────────────────────────────

class TestResult(Lenient):
    __test__ = False
    spec_file: str
    test_title: Optional[str] = None
    status: str
    duration_ms: Optional[Union[int, float]] = None
    flaky: Optional[bool] = None
    errors: List[Any] = Field(default_factory=list)


class ExecutionResultsV2(Lenient):
    schema_version: Literal[2] = 2
    artifact: Literal["execution_results"] = "execution_results"
    project: Optional[str] = None
    status: Optional[str] = None
    mode: Optional[str] = None
    base_url: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    returncode: Optional[int] = None
    report_json: Optional[str] = None
    results: List[TestResult] = Field(default_factory=list)


class MtaAttempt(Lenient):
    retry: int = 0
    status: str
    duration_ms: Optional[Union[int, float]] = None
    error: Optional[str] = None
    failed_step: Optional[str] = None   # Phase 4.5: the failed test.step (plan step) title


class MtaAttachment(Lenient):
    name: str
    content_type: Optional[str] = None
    path: Optional[str] = None


class MtaTest(Lenient):
    """One test in the MTA Playwright reporter's output (Phase 4.2)."""
    __test__ = False
    test_id: str
    title: str
    title_path: List[str] = Field(default_factory=list)
    spec_file: str
    line: Optional[int] = None
    project: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    annotations: List[Dict[str, Any]] = Field(default_factory=list)
    tc_id: Optional[str] = None
    case_id: Optional[str] = None
    scenario_id: Optional[str] = None
    ac_ids: List[str] = Field(default_factory=list)
    status: Literal["passed", "failed", "flaky", "skipped", "timedOut", "interrupted"]
    cleanup_failures: List[str] = Field(default_factory=list)   # Phase 4.4 cleanup fixture
    outcome: Optional[str] = None
    expected_status: Optional[str] = None
    retries: int = 0
    duration_ms: Optional[Union[int, float]] = None
    attempts: List[MtaAttempt] = Field(default_factory=list)
    attachments: List[MtaAttachment] = Field(default_factory=list)


class MtaResultsV2(Lenient):
    """test_execution/reports/mta/{ts}.mta_results.json — written by
    application_assets/_shared/runtime/reporters/mta-reporter.ts, read by tools/execution/mta_results.py."""
    schema_version: Literal[2] = 2
    artifact: Literal["mta_results"] = "mta_results"
    run_id: Optional[str] = None
    project: Optional[str] = None
    shard: Optional[Dict[str, int]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: Optional[str] = None
    totals: Dict[str, int] = Field(default_factory=dict)
    tests: List[MtaTest] = Field(default_factory=list)


class PlaywrightReportLoose(Lenient):
    """Playwright's own JSON reporter output — a third-party format, checked loosely."""
    config: Optional[Dict[str, Any]] = None
    suites: List[Any] = Field(default_factory=list)
    stats: Optional[Dict[str, Any]] = None


# ── locator_map.json (no envelope; read by the TS runtime) ───────────────────

class LocatorScope(Lenient):
    type: str
    locator: Optional[str] = None
    name: Optional[str] = None


class LocatorEntry(Lenient):
    type: str
    locator: Optional[str] = None
    name: Optional[str] = None
    frame: Optional[List[str]] = None              # Phase 2: frameLocator chain
    scope: Optional[LocatorScope] = None           # Phase 2: container-scoped locator


# ── requirements.json / traceability.json (Phase 1) ──────────────────────────
# New artifacts with no v1 variants on disk, so their contracts are the strict producer models from the
# shared requirements core (tools/requirements/models.py) rather than lenient copies.

from tools.requirements.models import RequirementsDoc as RequirementsV2  # noqa: E402
from tools.requirements.models import TraceabilityDoc as TraceabilityV2  # noqa: E402


# ── Phase 2 deep discovery artifacts ─────────────────────────────────────────
# New artifacts; contracts are the strict producer models in tools/discovery/deep/models.py.

from tools.discovery.deep.models import ApiInventoryDoc as ApiInventoryV2  # noqa: E402
from tools.discovery.deep.models import AppMapDoc as AppMapV2  # noqa: E402
from tools.discovery.deep.models import BaselineDoc as BaselineV2  # noqa: E402
from tools.discovery.deep.models import FormModelDoc as FormModelV2  # noqa: E402
from tools.discovery.deep.models import PermissionMatrixDoc as PermissionMatrixV2  # noqa: E402


# ── Phase 3 test design ──────────────────────────────────────────────────────
# New artifact; the contract is the strict producer model in tools/test_design/models.py.

from tools.test_design.models import TestCasesDoc as TestCasesV2  # noqa: E402
