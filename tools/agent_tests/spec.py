"""
spec.py — AgentSpec: everything the generators and the runner need to know about one agent under test.

Lives in eval_sets/<agent>/agent.yaml (design D3: the file's presence is the per-agent opt-in). It is written by a
human from the agent's BRD (buggy_bot) or drafted from a BRD and then reviewed. Generators read ONLY this spec plus
the curated catalogs, so the same spec + seed always produce the same cases.
"""

from typing import Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import Field, model_validator

from tools.agent_tests.config import (DEFAULT_BUDGETS, DEFAULT_GATE, DEFAULT_JUDGE, DEFAULT_REPEATS, DEFAULT_THRESHOLDS,
                                      REGRESSION, SAFETY_DIMENSIONS, SAFETY_GATE, STABILITY)
from tools.agent_tests.models import DIMENSIONS, Expected, Strict, ToolCallExpect


class TransportCfg(Strict):
    """How to send one message. Body placeholders: "{message}", "{session}", "{messages}" (client-side history)."""
    kind: Literal["http"] = "http"
    path: str = "/chat"
    method: Literal["POST", "PUT"] = "POST"
    body: Dict[str, Any] = Field(default_factory=lambda: {"message": "{message}"})
    output_path: Optional[str] = None
    trace_path: Optional[str] = None
    usage_path: Optional[str] = None
    history: Literal["server", "client", "none"] = "none"  # set server / client to enable multi-turn tests
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout_s: int = 60

    @model_validator(mode="after")
    def _history_shape(self):
        flat = yaml.safe_dump(self.body)
        if self.history == "server" and "{session}" not in flat:
            raise ValueError("transport.history 'server' needs a \"{session}\" placeholder in the body")
        if self.history == "client" and "{messages}" not in flat:
            raise ValueError("transport.history 'client' needs a \"{messages}\" placeholder in the body")
        if "://" in self.path or self.path.startswith("//"):
            raise ValueError("transport.path must be a path on the agent's own origin")
        return self

    @property
    def sessions(self) -> bool:
        return self.history in ("server", "client")


class Authorization(Strict):
    owned_or_authorized: bool = False
    by: Optional[str] = None
    note: Optional[str] = None


class CanaryCfg(Strict):
    system_prompt_env: Optional[str] = None    # MTA starts the agent and plants a per-run canary through this env var
    system_prompt_value: Optional[str] = None  # a marker the agent's owner planted and told us about

    @property
    def system_prompt_applicable(self) -> bool:
        return bool(self.system_prompt_env or self.system_prompt_value)


class Example(Strict):
    input: str
    expect: Expected
    title: Optional[str] = None
    paraphrases: List[str] = Field(default_factory=list)
    translations: List[str] = Field(default_factory=list)


class AcSpec(Strict):
    id: str
    statement: str
    examples: List[Example] = Field(default_factory=list)


class KbDoc(Strict):
    id: str
    title: str
    question: str
    facts: List[str]
    ac_ids: List[str] = Field(default_factory=list)


class Unanswerable(Strict):
    question: str
    ac_ids: List[str] = Field(default_factory=list)


class KbCfg(Strict):
    citation_format: Optional[str] = None  # e.g. "(Source: {title})"; None = the agent does not cite
    docs: List[KbDoc] = Field(default_factory=list)
    unanswerable: List[Unanswerable] = Field(default_factory=list)


class ScopeCfg(Strict):
    domain: str = ""
    out_of_domain: List[str] = Field(default_factory=list)
    use_catalog: bool = True


class PolicyCfg(Strict):
    refuse: List[str] = Field(default_factory=list)  # harmful-catalog categories the agent's policy refuses


class MemoryFact(Strict):
    kind: str                         # name | order | … (name / order also seed the session-isolation canaries)
    set: str                          # "Hi, my name is {value}."
    ask: str                          # "What is my name?"
    values: List[str] = Field(min_length=2)
    correction: Optional[str] = None  # "Sorry, my name is actually {value}."


class MemoryCfg(Strict):
    facts: List[MemoryFact] = Field(default_factory=list)


class JsonFormat(Strict):
    trigger: str
    schema_: Dict[str, Any] = Field(alias="schema")
    questions: List[str]
    ac_ids: List[str] = Field(default_factory=list)


class LengthFormat(Strict):
    max_words: int
    questions: List[str]
    ac_ids: List[str] = Field(default_factory=list)


class FormatCfg(Strict):
    json_: Optional[JsonFormat] = Field(default=None, alias="json")
    length: Optional[LengthFormat] = None


class ToolSpec(Strict):
    name: str
    authorized: bool = True


class ToolProbe(Strict):
    title: str
    input: str
    must_call: List[ToolCallExpect] = Field(default_factory=list)
    recovers_from_error: bool = False
    ac_ids: List[str] = Field(default_factory=list)


class ToolsCfg(Strict):
    available: List[ToolSpec] = Field(default_factory=list)
    probes: List[ToolProbe] = Field(default_factory=list)

    @property
    def unauthorized(self) -> List[str]:
        return sorted(t.name for t in self.available if not t.authorized)


class Budgets(Strict):
    p50_ms: Optional[float] = DEFAULT_BUDGETS["p50_ms"]
    p95_ms: Optional[float] = DEFAULT_BUDGETS["p95_ms"]
    max_tokens_per_turn_p95: Optional[float] = DEFAULT_BUDGETS["max_tokens_per_turn_p95"]
    max_requests: int = DEFAULT_BUDGETS["max_requests"]
    max_minutes: float = DEFAULT_BUDGETS["max_minutes"]
    ac_ids: List[str] = Field(default_factory=list)


class Thresholds(Strict):
    consistency_similarity: float = DEFAULT_THRESHOLDS["consistency_similarity"]
    consistency_n: int = DEFAULT_THRESHOLDS["consistency_n"]
    long_input_chars: int = DEFAULT_THRESHOLDS["long_input_chars"]
    multi_turn_turns: int = DEFAULT_THRESHOLDS["multi_turn_turns"]
    robustness_bases: int = DEFAULT_THRESHOLDS["robustness_bases"]


class GateCfg(Strict):
    min_lower_bound: float = Field(DEFAULT_GATE["min_lower_bound"], ge=0, le=1)
    max_failures: Optional[int] = None  # None = no absolute limit


class DimensionCfg(Strict):
    enabled: Union[bool, Literal["auto"]] = True
    min_cases: Optional[int] = None
    repeats: Optional[int] = Field(None, ge=1)   # k for this dimension (Phase 9.4)
    gate: Optional[GateCfg] = None


class JudgeCfg(Strict):
    connector: str = DEFAULT_JUDGE["connector"]
    model: Optional[str] = DEFAULT_JUDGE["model"]
    escalate: List[str] = Field(default_factory=lambda: list(DEFAULT_JUDGE["escalate"]))


class StabilityCfg(Strict):
    max_pass_rate_variance: float = STABILITY["max_pass_rate_variance"]


class RegressionCfg(Strict):
    max_drop_points: float = REGRESSION["max_drop_points"]


class AgentSpec(Strict):
    agent: str
    name: str
    agent_version: str = "unversioned"
    agent_model: Optional[str] = None  # the model behind the agent, when known: the judge must differ from it
    description: str = ""
    enabled: bool = True
    source: Literal["brd", "generated", "human"] = "brd"
    authorization: Authorization = Field(default_factory=Authorization)
    transport: TransportCfg = Field(default_factory=TransportCfg)
    canaries: CanaryCfg = Field(default_factory=CanaryCfg)
    acs: List[AcSpec] = Field(default_factory=list)
    kb: KbCfg = Field(default_factory=KbCfg)
    scope: ScopeCfg = Field(default_factory=ScopeCfg)
    policy: PolicyCfg = Field(default_factory=PolicyCfg)
    memory: MemoryCfg = Field(default_factory=MemoryCfg)
    format: FormatCfg = Field(default_factory=FormatCfg)
    tools: ToolsCfg = Field(default_factory=ToolsCfg)
    dimension_acs: Dict[str, List[str]] = Field(default_factory=dict)  # default AC links per dimension
    budgets: Budgets = Field(default_factory=Budgets)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    dimensions: Dict[str, DimensionCfg] = Field(default_factory=dict)
    judge: JudgeCfg = Field(default_factory=JudgeCfg)
    stability: StabilityCfg = Field(default_factory=StabilityCfg)
    regression: RegressionCfg = Field(default_factory=RegressionCfg)

    @model_validator(mode="after")
    def _known_dimensions(self):
        for d in list(self.dimensions) + list(self.dimension_acs):
            if d not in DIMENSIONS:
                raise ValueError(f"unknown dimension {d!r}")
        return self

    def acs_for(self, dimension: str) -> List[str]:
        return list(self.dimension_acs.get(dimension, []))

    def repeats_for(self, dimension: str) -> int:
        cfg = self.dimensions.get(dimension)
        return (cfg.repeats if cfg and cfg.repeats else DEFAULT_REPEATS[dimension])

    def gate_for(self, dimension: str) -> GateCfg:
        cfg = self.dimensions.get(dimension)
        if cfg and cfg.gate:
            return cfg.gate
        return GateCfg(**(SAFETY_GATE if dimension in SAFETY_DIMENSIONS else DEFAULT_GATE))

    def dimension_enabled(self, dimension: str) -> bool:
        flag = self.dimensions.get(dimension, DimensionCfg()).enabled
        if flag == "auto" or (dimension == "tool_use" and dimension not in self.dimensions):
            return bool(self.transport.trace_path) if dimension == "tool_use" else True
        return bool(flag)


def load_spec(path: str) -> AgentSpec:
    with open(path, encoding="utf-8") as f:
        return AgentSpec.model_validate(yaml.safe_load(f) or {})
