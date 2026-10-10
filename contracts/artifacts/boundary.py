"""
boundary.py — contract validation at orchestrator step boundaries (Phase 0.7).

After each step, the artifacts that step produces are validated against their
contracts. Mode comes from project.yaml `contracts.enforce`:

    warn  (default) — violations become `partial_reasons` on the step result; the
                      run continues.
    block           — the step becomes status=failed, blocking=True, which stops the
                      run through the orchestrator's existing blocking-failure path.

A missing artifact is not a contract violation (steps legitimately skip outputs;
the discovery step has its own mandatory-output gate).
"""

import glob
import os
from typing import Any, Dict, List, Optional

from contracts.artifacts.io import ValidationReport, validate_file
from contracts.artifacts.paths import COMPREHENSION_DIRS, REPORTS_MTA, artifact_path

STEP_ARTIFACTS: Dict[str, List[str]] = {
    "discovery": ["business_scenarios", "dom_elements"],
    "comprehension": ["business_scenarios"],
    "testdata": ["test_data"],
    "semantic_map": ["scenario_element_map"],
    "script_generation": ["test_plans", "test_suite", "locator_map"],
    "ui_execution": ["execution_results", "playwright_report"],
    "execution": ["execution_results", "playwright_report"],
    "healing": ["test_suite", "locator_map"],
    "reporting": ["test_suite"],
}


def _latest(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def _paths_for(project_dir: str, name: str, result: Optional[Dict[str, Any]]) -> List[str]:
    if name == "dom_elements":
        out = []
        for d in COMPREHENSION_DIRS:
            root = os.path.join(project_dir, d, "dom_elements.json")
            if os.path.exists(root):
                out.append(root)
            out += sorted(glob.glob(os.path.join(project_dir, d, "modules", "*", "dom_elements.json")))
        return out
    if name == "playwright_report":
        path = (result or {}).get("report_json")
        return [path] if path and os.path.exists(path) else []
    if name == "execution_results":
        latest = _latest(os.path.join(project_dir, REPORTS_MTA, "*.execution_results.json"))
        return [latest] if latest else []
    path = artifact_path(project_dir, name, existing_only=True)
    return [path] if path else []


def validate_step_outputs(project_dir: str, step: str,
                          result: Optional[Dict[str, Any]] = None) -> List[ValidationReport]:
    """Validation reports for every artifact *step* produced that exists on disk."""
    reports: List[ValidationReport] = []
    for name in STEP_ARTIFACTS.get(step, []):
        for path in _paths_for(project_dir, name, result):
            reports.append(validate_file(name, path))
    return reports


def apply_enforcement(result: Dict[str, Any], reports: List[ValidationReport], mode: str) -> Dict[str, Any]:
    """Fold failing reports into the step *result* (returns a new dict)."""
    failures = [r for r in reports if not r.ok]
    out = dict(result)
    out["contract_checks"] = {
        "checked": len(reports), "failed": len(failures), "mode": mode,
        "violations": [r.as_dict() for r in failures],
    }
    if not failures:
        return out
    messages = [f"contract violation: {r.artifact} ({r.path}): {'; '.join(r.errors[:3])}" for r in failures]
    if mode == "block":
        out["status"] = "failed"
        out["blocking"] = True
        out["error"] = messages[0] if len(messages) == 1 else f"{len(messages)} contract violations: {messages[0]} ..."
    else:
        if out.get("status", "success") == "success":
            out["status"] = "partial"
        out["partial_reasons"] = list(out.get("partial_reasons") or []) + messages
    return out
