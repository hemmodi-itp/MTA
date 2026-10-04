import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import yaml


@dataclass
class WorkflowDefinition:
    workflow_id: str
    steps: List[str]
    always_run: Set[str] = field(default_factory=set)
    # Optional DAG metadata (agent_evaluation.yaml). Workflows without it keep running strictly in order.
    needs: Dict[str, List[str]] = field(default_factory=dict)      # step -> steps it waits for
    critical: Set[str] = field(default_factory=set)                # a failure here stops the run
    timeout_s: Dict[str, int] = field(default_factory=dict)        # soft per-step deadline (seconds)
    provides: Dict[str, List[str]] = field(default_factory=dict)   # step -> result keys it may write

    @property
    def is_dag(self) -> bool:
        return bool(self.needs)

    def deps(self, step: str) -> List[str]:
        """Steps `step` waits for; sequential workflows depend on the previous step."""
        if self.is_dag:
            return list(self.needs.get(step, []))
        i = self.steps.index(step)
        return [self.steps[i - 1]] if i else []


def load_workflow(workflow_name: str) -> WorkflowDefinition:
    workflow_file = os.path.join(os.path.dirname(__file__), f"{workflow_name}.yaml")
    if not os.path.exists(workflow_file):
        raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

    with open(workflow_file, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    raw_steps = data.get("steps", [])
    if not isinstance(raw_steps, list):
        raise ValueError("Workflow steps must be a list")

    wf = WorkflowDefinition(workflow_id=workflow_name, steps=[])
    for entry in raw_steps:
        if isinstance(entry, str):
            wf.steps.append(entry)
            continue
        name = entry["name"]
        wf.steps.append(name)
        if entry.get("always_run"):
            wf.always_run.add(name)
        if "needs" in entry:
            wf.needs[name] = list(entry.get("needs") or [])
        if entry.get("critical"):
            wf.critical.add(name)
        if entry.get("timeout_s"):
            wf.timeout_s[name] = int(entry["timeout_s"])
        if entry.get("provides"):
            wf.provides[name] = list(entry["provides"])

    if wf.needs:
        _validate_dag(wf)
    return wf


def _validate_dag(wf: WorkflowDefinition) -> None:
    known = set(wf.steps)
    for step in wf.steps:
        wf.needs.setdefault(step, [])
        unknown = [d for d in wf.needs[step] if d not in known]
        if unknown:
            raise ValueError(f"Workflow {wf.workflow_id}: step {step} needs unknown step(s) {unknown}")
    # cycle check (Kahn)
    indeg = {s: len(wf.needs[s]) for s in wf.steps}
    ready = [s for s in wf.steps if indeg[s] == 0]
    seen = 0
    while ready:
        s = ready.pop()
        seen += 1
        for t in wf.steps:
            if s in wf.needs[t]:
                indeg[t] -= 1
                if indeg[t] == 0:
                    ready.append(t)
    if seen != len(wf.steps):
        raise ValueError(f"Workflow {wf.workflow_id}: dependency cycle")
    # two steps may only write the same result key when one depends (transitively) on the other
    owners: Dict[str, List[str]] = {}
    for step, keys in wf.provides.items():
        for k in keys:
            owners.setdefault(k, []).append(step)
    for key, steps in owners.items():
        for i, a in enumerate(steps):
            for b in steps[i + 1:]:
                if not (_reaches(wf, a, b) or _reaches(wf, b, a)):
                    raise ValueError(f"Workflow {wf.workflow_id}: steps {a} and {b} both write '{key}' and can run "
                                     "concurrently")


def _reaches(wf: WorkflowDefinition, src: str, dst: str, _seen: Optional[Set[str]] = None) -> bool:
    """True when dst (transitively) needs src."""
    _seen = _seen if _seen is not None else set()
    for d in wf.needs.get(dst, []):
        if d == src:
            return True
        if d not in _seen:
            _seen.add(d)
            if _reaches(wf, src, d, _seen):
                return True
    return False
