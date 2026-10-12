"""
models.py — the golden-dataset record for AI-agent tests (Phase 9.2) and its closed vocabularies.

One AgentTestCase per line in eval_sets/<agent>/<dimension>.jsonl. `expected` holds only deterministic assertions
(checked by tools/agent_tests/checks); `rubric` is what an LLM judge would grade (Phase 9.3) when the deterministic
checks cannot decide. Run-time tokens are written as placeholders ({{RUN_MARKER}} …) and substituted per run, so a
reviewed dataset never changes when canaries rotate.
"""

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DIMENSIONS: tuple[str, ...] = (
    "task_success", "groundedness", "hallucination", "consistency", "robustness", "multi_turn",
    "instruction_format", "scope", "prompt_injection_direct", "prompt_injection_indirect", "data_leakage",
    "harmful_refusal", "tool_use", "session_isolation", "latency_cost",
)
ABBR: Dict[str, str] = {
    "task_success": "TASK", "groundedness": "GRND", "hallucination": "HALL", "consistency": "CONS",
    "robustness": "ROBU", "multi_turn": "MTRN", "instruction_format": "FRMT", "scope": "SCOP",
    "prompt_injection_direct": "INJD", "prompt_injection_indirect": "INJI", "data_leakage": "LEAK",
    "harmful_refusal": "HARM", "tool_use": "TOOL", "session_isolation": "SESS", "latency_cost": "LATC",
}
# Red-team dimensions run only against agents the owner has authorised (D10).
RED_TEAM: frozenset = frozenset({"prompt_injection_direct", "prompt_injection_indirect", "data_leakage",
                                 "harmful_refusal", "session_isolation"})

PLACEHOLDERS: tuple[str, ...] = ("RUN_MARKER", "RUN_MARKER_B64", "CANARY_SYS", "SESSION_CANARY_NAME",
                                 "SESSION_CANARY_ORDER")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Z_]+)\s*\}\}")
REFUSAL_KINDS = ("dont_know", "refusal", "redirect")
SCHEMA_VERSION = 1
_REVIEW_FIELDS = {"reviewed", "reviewed_by", "reviewed_at", "content_hash"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolCallExpect(Strict):
    tool: str
    args: Optional[Dict[str, Any]] = None  # every given key must equal the traced argument


class TraceExpect(Strict):
    must_call: List[ToolCallExpect] = Field(default_factory=list)
    must_not_call: List[str] = Field(default_factory=list)
    recovers_from_error: bool = False  # a tool failed and the reply still handled it gracefully


class Expected(Strict):
    """Deterministic assertions on the reply (the last reply for multi-turn cases)."""
    contains_all: Optional[List[str]] = None
    contains_any: Optional[List[str]] = None
    not_contains: Optional[List[str]] = None
    regex: Optional[str] = None
    not_regex: Optional[str] = None
    refusal: Optional[List[Literal["dont_know", "refusal", "redirect"]]] = None
    graceful: Optional[bool] = None
    json_schema: Optional[Dict[str, Any]] = None
    max_words: Optional[int] = None
    canary_absent: Optional[List[str]] = None  # placeholder names whose run token must not appear (any encoding)
    cites: Optional[str] = None  # the citation text the reply must carry, e.g. "(Source: Store hours)"
    same_as: Optional[str] = None  # robustness: the base case whose verdict this variant must reproduce
    consistent_n: Optional[int] = None  # consistency: send the input this many times in fresh sessions
    trace: Optional[TraceExpect] = None

    @field_validator("canary_absent")
    @classmethod
    def _known_tokens(cls, v):
        for name in v or []:
            if name not in PLACEHOLDERS:
                raise ValueError(f"unknown canary placeholder {name!r} (allowed: {', '.join(PLACEHOLDERS)})")
        return v

    def is_empty(self) -> bool:
        return not any(v not in (None, [], False) for k, v in self.model_dump().items() if k != "same_as")


class Turn(Strict):
    user: str
    session: str = "A"
    expected: Optional[Expected] = None  # checked on this turn's reply (the final turn also uses the case's)


class AgentTestCase(Strict):
    id: str
    dimension: Literal[DIMENSIONS]  # type: ignore[valid-type]
    schema_version: int = SCHEMA_VERSION
    title: str
    input: Optional[str] = None
    turns: Optional[List[Turn]] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    expected: Expected = Field(default_factory=Expected)
    rubric: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    ac_ids: List[str] = Field(default_factory=list)
    source: Literal["brd", "generated", "human"]
    reviewed: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    repeats: Optional[int] = None  # k for this case (Phase 9.4); None = the dimension default
    content_hash: Optional[str] = None

    @model_validator(mode="after")
    def _shape(self):
        if (self.input is None) == (self.turns is None):
            raise ValueError("exactly one of `input` and `turns` must be set")
        if self.turns is not None and not self.turns:
            raise ValueError("`turns` must not be empty")
        if self.source == "brd" and not self.ac_ids:
            raise ValueError("a case with source 'brd' must name its acceptance criteria (ac_ids)")
        for ac in self.ac_ids:
            if not re.fullmatch(r"AC-\d+\.\d+", ac):
                raise ValueError(f"malformed acceptance-criterion id {ac!r} (expected AC-<n>.<m>)")
        unknown = sorted(set(_PLACEHOLDER_RE.findall(json.dumps(self.model_dump(exclude={"content_hash"})))) -
                         set(PLACEHOLDERS))
        if unknown:
            raise ValueError(f"unknown placeholder(s): {', '.join(unknown)}")
        if self.expected.is_empty() and not self.rubric and self.dimension != "latency_cost":
            raise ValueError("a case needs at least one deterministic expectation or a rubric")
        return self

    def compute_hash(self) -> str:
        return content_hash(self.model_dump(exclude_none=False))

    def with_hash(self) -> "AgentTestCase":
        return self.model_copy(update={"content_hash": self.compute_hash()})


def content_hash(record: Dict[str, Any]) -> str:
    """SHA-256 over the case content, ignoring review bookkeeping (so marking a case reviewed keeps its hash)."""
    body = {k: v for k, v in record.items() if k not in _REVIEW_FIELDS}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def placeholders_in(text: str) -> List[str]:
    return _PLACEHOLDER_RE.findall(text or "")


def substitute(value: Any, tokens: Dict[str, str]) -> Any:
    """Replace {{NAME}} placeholders in every string inside *value* (dicts / lists walked recursively)."""
    if isinstance(value, str):
        return _PLACEHOLDER_RE.sub(lambda m: tokens.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [substitute(v, tokens) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, tokens) for k, v in value.items()}
    return value


SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema", f"agent_test_case.v{SCHEMA_VERSION}.schema.json")


def export_schema() -> str:
    """JSON Schema of one dataset line (committed under tools/agent_tests/schema/; a test keeps it fresh)."""
    schema = AgentTestCase.model_json_schema()
    schema["$id"] = f"mta:agent_test_case:v{SCHEMA_VERSION}"
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
