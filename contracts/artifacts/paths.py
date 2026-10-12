"""
paths.py — where each artifact lives inside a project directory.

Current layout writes comprehension output to `test_comprehension/`; older
projects still hold it in `comprehension/` (and sauceLabs has both). Lookups try
the current directory first, then the legacy one.
"""

import glob
import os
from typing import Iterator, List, Optional, Tuple

COMPREHENSION_DIRS = ("test_comprehension", "comprehension")

_FIXED = {
    "test_data": os.path.join("test_creation", "test_data", "test_data.json"),
    "scenario_element_map": os.path.join("test_creation", "scenario_element_map.json"),
    "test_plans": os.path.join("test_creation", "test_plans.json"),
    "test_suite": os.path.join("test_creation", "test_suite.json"),
    "locator_map": os.path.join("test_creation", "locator_map.json"),
    "traceability": os.path.join("test_creation", "traceability.json"),
    "test_cases": os.path.join("test_creation", "test_cases.json"),
}
_COMPREHENSION = {
    "dom_elements": "dom_elements.json",
    "business_scenarios": "business_scenarios.json",
    "requirements": "requirements.json",
    # Phase 2 deep discovery (project-level)
    "app_map": "app_map.json",
    "form_model": "form_model.json",
    "api_inventory": "api_inventory.json",
    "permission_matrix": "permission_matrix.json",
    "baseline": "baseline.json",
}
REPORTS_JSON = os.path.join("test_execution", "reports", "json")
# MTA-normalised run records live apart from Playwright's JSON: HealingAgent and
# the report index pick "the latest *_results.json" in reports/json/.
REPORTS_MTA = os.path.join("test_execution", "reports", "mta")


def artifact_path(project_dir: str, name: str, existing_only: bool = False) -> Optional[str]:
    """Canonical path of a single-instance artifact (current layout first)."""
    if name in _FIXED:
        path = os.path.join(project_dir, _FIXED[name])
        return path if (not existing_only or os.path.exists(path)) else None
    if name in _COMPREHENSION:
        for d in COMPREHENSION_DIRS:
            path = os.path.join(project_dir, d, _COMPREHENSION[name])
            if os.path.exists(path):
                return path
        return None if existing_only else os.path.join(project_dir, COMPREHENSION_DIRS[0], _COMPREHENSION[name])
    raise KeyError(f"artifact '{name}' has no single fixed path")


def iter_project_artifacts(project_dir: str) -> Iterator[Tuple[str, str]]:
    """Every artifact file present in a project: (artifact_name, path)."""
    for name, rel in _FIXED.items():
        path = os.path.join(project_dir, rel)
        if os.path.exists(path):
            yield name, path
    for d in COMPREHENSION_DIRS:
        for name, fname in _COMPREHENSION.items():
            path = os.path.join(project_dir, d, fname)
            if os.path.exists(path):
                yield name, path
        for path in sorted(glob.glob(os.path.join(project_dir, d, "modules", "*", "dom_elements.json"))):
            yield "dom_elements", path
    reports = os.path.join(project_dir, REPORTS_JSON)
    for path in sorted(glob.glob(os.path.join(reports, "*_results.json"))):
        yield "playwright_report", path
    for path in sorted(glob.glob(os.path.join(project_dir, REPORTS_MTA, "*.execution_results.json"))):
        yield "execution_results", path
    for path in sorted(glob.glob(os.path.join(project_dir, REPORTS_MTA, "*.mta_results.json"))):
        yield "mta_results", path


def project_dirs(root: str) -> List[str]:
    if not os.path.isdir(root):
        return []
    return sorted(
        os.path.join(root, d) for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d)) and not d.startswith(".")
    )
