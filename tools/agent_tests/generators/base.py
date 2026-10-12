"""
base.py — shared helpers for the per-dimension generators.

Every generator is a pure function generate(spec, catalogs, seed) -> GeneratorResult. Determinism rules (design D6):
  * case id = AT-<DIM>-<8 hex of SHA-1 over the case's content key> — stable across processes and hash seeds;
  * any randomness comes from rng(seed, key) = random.Random("<seed>:<key>") (string seeding is hash-seed independent);
  * no timestamps, no dict-order dependence: cases come out in a fixed order.
"""

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List

from tools.agent_tests.config import MIN_CASES
from tools.agent_tests.models import ABBR, AgentTestCase, canonical_json


@dataclass
class GeneratorResult:
    dimension: str
    cases: List[AgentTestCase] = field(default_factory=list)
    cut: List[Dict[str, Any]] = field(default_factory=list)  # {dimension, reason, detail}

    def note(self, reason: str, detail: str) -> None:
        self.cut.append({"dimension": self.dimension, "reason": reason, "detail": detail})


def case_id(dimension: str, key: Dict[str, Any]) -> str:
    digest = hashlib.sha1(canonical_json({"dimension": dimension, **key}).encode("utf-8")).hexdigest()
    return f"AT-{ABBR[dimension]}-{digest[:8]}"


def make_case(dimension: str, key: Dict[str, Any], **fields: Any) -> AgentTestCase:
    return AgentTestCase(id=case_id(dimension, key), dimension=dimension, **fields).with_hash()


def rng(seed: int, key: str) -> random.Random:
    return random.Random(f"{seed}:{key}")


def check_minimum(result: GeneratorResult, spec) -> None:
    cfg = spec.dimensions.get(result.dimension)
    minimum = (cfg.min_cases if cfg and cfg.min_cases is not None else MIN_CASES[result.dimension])
    if len(result.cases) < minimum:
        result.note("spec_lacks_material",
                    f"produced {len(result.cases)} case(s), below the minimum of {minimum}: add material to agent.yaml")


def dedupe(cases: List[AgentTestCase]) -> List[AgentTestCase]:
    seen, out = set(), []
    for c in cases:
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
    return out
