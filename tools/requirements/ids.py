"""
ids.py — stable identifiers for requirements, acceptance criteria and test cases (Phase 1).

  * Document ids (REQ-01, AC-01.2) are canonical and used as-is (design R2).
  * Generated ids for content without one are project-wide, content-keyed and persisted in the project's
    artifact_registry.json: the same content gets the same id on every run, new content the next number, and a
    number the document already uses is skipped.
        requirement        REQ-007            (3 digits, scope "REQ")
        criterion          AC-03.5 / AC-007.2 (under its requirement's number, scope "AC:<req>")
        atomic child       AC-03.2.1          (under its parent criterion, scope "CHILD:<parent>")
        test case          M01_TC_003         (module-namespaced, like scenario ids)
"""

import re
from typing import Iterable, Optional

from tools.state.artifact_registry import ArtifactRegistry


def number_part(identifier: str) -> str:
    """'REQ-01' -> '01', 'AC-03.2' -> '03.2'."""
    return identifier.split("-", 1)[1] if "-" in identifier else identifier


def _ints(values: Iterable[str]) -> set:
    out = set()
    for v in values:
        m = re.search(r"(\d+)$", v or "")
        if m:
            out.add(int(m.group(1)))
    return out


class IdAllocator:
    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry

    def requirement_id(self, title: str, description: str, taken_ids: Iterable[str] = ()) -> str:
        n, _ = self.registry.get_or_create_sequence_number("REQ", title, description, taken=_ints(taken_ids))
        return f"REQ-{n:03d}"

    def criterion_id(self, req_id: str, statement: str, taken_ids: Iterable[str] = ()) -> str:
        k, _ = self.registry.get_or_create_sequence_number(f"AC:{req_id}", statement, taken=_ints(taken_ids))
        return f"AC-{number_part(req_id)}.{k}"

    def child_id(self, parent_id: str, statement: str, taken_ids: Iterable[str] = ()) -> str:
        k, _ = self.registry.get_or_create_sequence_number(f"CHILD:{parent_id}", statement,
                                                           taken=_ints(taken_ids))
        return f"{parent_id}.{k}"

    def test_case_id(self, module_id: Optional[str], scenario_id: str, name: str, test_type: str) -> str:
        tc_id, _, _ = self.registry.get_or_create_id(module_id or "GEN", "TC", scenario_id, name, test_type or "")
        return tc_id

    def save(self) -> None:
        self.registry.save()
