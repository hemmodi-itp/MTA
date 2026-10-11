"""
models.py — contracts of the five Phase 2 artifacts (schema_version 2, dict envelope).

New artifacts with no v1 variants on disk, so — like requirements/traceability in Phase 1 —
their contracts are these producer models (registered in contracts/artifacts/registry.py).
Top-level structure is strict (extra="forbid"); element dicts inside app_map states keep the
lenient dom_elements element shape (Dict[str, Any]).

    test_comprehension/app_map.json            task 2.4 states + transitions
    test_comprehension/form_model.json         task 2.3 observed validation oracle
    test_comprehension/api_inventory.json      task 2.5 network inventory
    test_comprehension/permission_matrix.json  task 2.6 role diff
    test_comprehension/baseline.json           task 2.7 console / page errors / timing
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── app_map.json ─────────────────────────────────────────────────────────────

Access = Literal["reachable", "blocked", "not_found", "error"]


class RevealedBy(_Strict):
    from_state: str
    element: Dict[str, Any]          # {ref, role, name, entry}


class AppState(_Strict):
    state_id: str
    url: str
    url_template: str
    title: str = ""
    kind: Literal["page", "revealed"] = "page"
    revealed_by: Optional[RevealedBy] = None
    status: Optional[int] = None
    access: Access = "reachable"
    structural_hash: str
    roles: List[str] = Field(default_factory=list)
    elements: List[Dict[str, Any]] = Field(default_factory=list)
    forms: List[str] = Field(default_factory=list)
    first_seen_depth: int = 0
    seed: Optional[str] = None


class Transition(_Strict):
    from_state: str
    to_state: Optional[str] = None
    action: Literal["navigate", "click", "expand"]
    element: Dict[str, Any] = Field(default_factory=dict)
    via: Literal["href", "click"] = "href"
    roles: List[str] = Field(default_factory=list)
    resolved_by_template: bool = False
    unresolved_reason: Optional[str] = None


class Skipped(_Strict):
    role: Optional[str] = None
    url: Optional[str] = None
    element: Optional[str] = None
    reason: str


class AppMapDoc(_Strict):
    schema_version: Literal[2] = 2
    artifact: Literal["app_map"] = "app_map"
    project: str
    generated_at: str
    config_hash: str
    seeds: List[str] = Field(default_factory=list)
    roles: List[Dict[str, Any]] = Field(default_factory=list)      # [{name, strategy}] — never secrets
    bounds: Dict[str, Any] = Field(default_factory=dict)
    stopped_by: Dict[str, str] = Field(default_factory=dict)
    duration_s: float = 0.0
    states: List[AppState] = Field(default_factory=list)
    transitions: List[Transition] = Field(default_factory=list)
    skipped: List[Skipped] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


# ── form_model.json ──────────────────────────────────────────────────────────

class VisibleError(_Strict):
    text: str
    container: Optional[str] = None
    role: Optional[str] = None
    field: Optional[str] = None
    attribution: Optional[str] = None


class ProbeNetwork(_Strict):
    method: str
    path: str
    status: Optional[int] = None
    aborted: bool = False


class Probe(_Strict):
    probe: str                       # empty | required_missing | too_long | wrong_type | below_min | above_max | non_integer | wrong_accept
    field: Optional[str] = None
    value_rule: str = ""
    submitted_via: str = ""
    native: Dict[str, Any] = Field(default_factory=dict)      # {blocked, messages: {field: msg|None}}
    visible_errors: List[VisibleError] = Field(default_factory=list)
    aria_invalid: List[str] = Field(default_factory=list)
    focused: Optional[str] = None
    network: List[ProbeNetwork] = Field(default_factory=list)
    url_before: str = ""
    url_after: str = ""
    navigated: bool = False
    accepted: bool = False
    error: Optional[str] = None
    duration_ms: int = 0


class FormField(_Strict):
    name: str
    label: str = ""
    type: str = ""
    locator: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    observed_messages: Dict[str, Any] = Field(default_factory=dict)


class FormRecord(_Strict):
    form_id: str
    state_id: str
    url: str
    url_template: str
    role: str
    dom_id: Optional[str] = None
    kind: Literal["form", "virtual"] = "form"
    method: str = "get"
    action: Optional[str] = None
    novalidate: bool = False
    submit: Dict[str, Any] = Field(default_factory=dict)
    fields: List[FormField] = Field(default_factory=list)
    probes: List[Probe] = Field(default_factory=list)
    skipped_probes: List[Dict[str, Any]] = Field(default_factory=list)


class SkippedForm(_Strict):
    form_id: Optional[str] = None
    state_id: str
    form: str
    reason: str


class FormModelDoc(_Strict):
    schema_version: Literal[2] = 2
    artifact: Literal["form_model"] = "form_model"
    project: str
    generated_at: str
    environment: str
    probe_mode: Literal["full", "client_only", "disabled"]
    browser: str = ""
    locale: str = ""
    forms: List[FormRecord] = Field(default_factory=list)
    skipped_forms: List[SkippedForm] = Field(default_factory=list)


# ── api_inventory.json ───────────────────────────────────────────────────────

class Endpoint(_Strict):
    method: str
    path_template: str
    kind: Literal["page", "form_submit", "xhr", "fetch", "other"]
    statuses: Dict[str, int] = Field(default_factory=dict)
    hosts: List[str] = Field(default_factory=list)
    auth: Dict[str, bool] = Field(default_factory=dict)
    request: Dict[str, Any] = Field(default_factory=dict)
    response: Dict[str, Any] = Field(default_factory=dict)
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    samples: int = 0
    aborted: int = 0
    roles: List[str] = Field(default_factory=list)


class ApiInventoryDoc(_Strict):
    schema_version: Literal[2] = 2
    artifact: Literal["api_inventory"] = "api_inventory"
    project: str
    generated_at: str
    endpoints: List[Endpoint] = Field(default_factory=list)


# ── permission_matrix.json ───────────────────────────────────────────────────

class StateAccess(_Strict):
    url_template: str
    sample_url: str
    access: Dict[str, str] = Field(default_factory=dict)     # role -> reachable | reachable_unlinked | blocked | not_found | unknown
    evidence: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ActionVisibility(_Strict):
    url_template: str
    element: Dict[str, Any]          # {role, name}
    visibility: Dict[str, str] = Field(default_factory=dict)  # role -> visible | hidden | blocked | not_found | unknown
    differs: bool = False


class PermissionMatrixDoc(_Strict):
    schema_version: Literal[2] = 2
    artifact: Literal["permission_matrix"] = "permission_matrix"
    project: str
    generated_at: str
    roles: List[str] = Field(default_factory=list)
    states: List[StateAccess] = Field(default_factory=list)
    actions: List[ActionVisibility] = Field(default_factory=list)


# ── baseline.json ────────────────────────────────────────────────────────────

class StateBaseline(_Strict):
    url: str
    role: str
    console_errors: List[Dict[str, Any]] = Field(default_factory=list)
    console_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    page_errors: List[Dict[str, Any]] = Field(default_factory=list)
    failed_requests: List[Dict[str, Any]] = Field(default_factory=list)
    timing: Dict[str, Any] = Field(default_factory=dict)


class BaselineDoc(_Strict):
    schema_version: Literal[2] = 2
    artifact: Literal["baseline"] = "baseline"
    project: str
    generated_at: str
    browser: str = ""
    states: Dict[str, StateBaseline] = Field(default_factory=dict)
