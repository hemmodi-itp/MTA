"""
tracing.py — annotate generated test plans with test-case ids and acceptance-criterion links (Phase 1.2 / 1.3).

Used by ScriptGenerationAgent when `requirements.enabled` is on and requirements.json exists:

  prompt_block(scenario)            the scenario's ACs for the plan prompt (empty when it has none)
  annotate(plan, scenario, module)  per test: tc_id, ac_ids, ac_link, req_ids, priority, title
  record_drops(plan, ...)           placeholder-negative / locator-type drops → plan["dropped_tests"]

The renderer turns these fields into the Playwright details object; traceability.json is rebuilt from them.
"""

from typing import Any, Dict, List, Optional

from tools.requirements.config import project_dir, requirements_enabled
from tools.requirements.ids import IdAllocator
from tools.requirements.linking import criteria_index, expand_to_leaves, link_scenario, link_test
from tools.requirements.models import RequirementsDoc
from tools.requirements.store import load_requirements
from tools.state.artifact_registry import ArtifactRegistry

_PROMPT_BLOCK = """

== Acceptance criteria this scenario covers (requirements.json) ==
{criteria}
For EVERY test add "ac_ids": the ids from this list that the test verifies (at least one). Use only ids from
this list — never invent one."""


class PlanTracer:
    def __init__(self, safe_project: str, doc: RequirementsDoc, registry: Optional[ArtifactRegistry] = None):
        self.safe_project = safe_project
        self.doc = doc
        self.index = criteria_index(doc)
        self.req_of = {ac.id: r.id for r in doc.requirements for ac in r.acceptance_criteria}
        self.allocator = IdAllocator(registry or ArtifactRegistry(project_dir(safe_project)))
        self.design_cases: Dict[str, Dict[str, Any]] = {}

    def set_design_cases(self, cases: List[Dict[str, Any]]) -> None:
        """Phase 3: tests carrying a `case_id` take their ACs, priority and technique from test_cases.json."""
        self.design_cases = {c["id"]: c for c in cases if c.get("id")}

    @classmethod
    def for_project(cls, safe_project: str, request: Optional[dict] = None, logger=None) -> Optional["PlanTracer"]:
        if not requirements_enabled(safe_project, request):
            return None
        try:
            doc = load_requirements(safe_project)
        except Exception as exc:    # an unreadable requirements.json must not stop generation
            if logger:
                logger.warning(f"[requirements] requirements.json unreadable — tests are not traced: {exc}")
            return None
        if doc is None or not doc.requirements:
            if logger:
                logger.warning("[requirements] requirements.enabled is on but requirements.json is missing or "
                               "empty — run discovery (or python -m tools.requirements.build) first")
            return None
        return cls(safe_project, doc)

    def scenario_acs(self, scenario: Dict[str, Any]) -> List[str]:
        leaves, _ = expand_to_leaves(scenario.get("ac_ids") or [], self.index)
        if not leaves:
            # Linked before the criteria it exercises existed (e.g. another module's): re-link now, in memory.
            leaves = link_scenario(scenario, self.doc).get("ac_ids") or []
        return leaves

    def prompt_block(self, scenario: Dict[str, Any]) -> str:
        acs = self.scenario_acs(scenario)
        if not acs:
            return ""
        return _PROMPT_BLOCK.format(criteria="\n".join(f"- {a}: {self.index[a].statement}" for a in acs))

    def annotate(self, plan: Dict[str, Any], scenario: Dict[str, Any], module_id: Optional[str]) -> Dict[str, Any]:
        from tools.test_creation.script_generator.spec_renderer import render_test_title

        sid = scenario.get("scenario_id", "")
        allowed = self.scenario_acs(scenario)
        tests = []
        for test in plan.get("tests") or []:
            t = dict(test)
            case = self.design_cases.get(t.get("case_id") or "")
            if case is not None:
                ac_ids, _ = expand_to_leaves(case.get("ac_ids") or [], self.index)
                link = "direct" if ac_ids else ""
                if not ac_ids:          # a design case with no AC: fall back to the scenario's criteria
                    ac_ids, link = link_test(t, allowed, self.index)
                t["technique"] = case.get("technique")
            else:
                ac_ids, link = link_test(t, allowed, self.index)
            t["ac_ids"] = ac_ids
            t["ac_link"] = link or None
            t["req_ids"] = list(dict.fromkeys(self.req_of[a] for a in ac_ids if a in self.req_of))
            priorities = [self.index[a].priority for a in ac_ids if a in self.index]
            t["priority"] = min(priorities, key=lambda p: int(p[1])) if priorities else None
            if case is not None:
                t["priority"] = case.get("priority") or t["priority"]     # risk-based (Phase 3.4)
            t["tc_id"] = self.allocator.test_case_id(module_id, sid, t.get("name", ""), t.get("type", ""))
            t["title"] = render_test_title(t)
            tests.append(t)
        out = dict(plan)
        out["tests"] = tests
        return out

    def save(self) -> None:
        self.allocator.save()


def record_drops(plan: Dict[str, Any], placeholder_dropped: List[str], mismatched: List[str]) -> Dict[str, Any]:
    """Record test drops made by ScriptGeneration's post-validation guards (reasons for the traceability report)."""
    entries = [{"test": name, "reason": "placeholder_negative_dropped"} for name in placeholder_dropped or []]
    entries += [{"test": d.split(":", 1)[0], "reason": "locator_type_mismatch", "detail": d} for d in mismatched or []]
    if not entries:
        return plan
    out = dict(plan)
    out["dropped_tests"] = list(plan.get("dropped_tests") or []) + entries
    return out
