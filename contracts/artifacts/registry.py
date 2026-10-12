"""
registry.py — the artifact catalogue: name -> model, envelope kind, file name.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Type

from pydantic import BaseModel

from contracts.artifacts import models as m


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    model: Type[BaseModel]
    filename: str
    # "dict"  -> v1 is a dict; v2 adds schema_version/artifact in place
    # "list"  -> v1 is a list; v2 moves it under `payload_key`
    # "map"   -> v1 is an id-keyed dict; v2 moves it under `payload_key`
    # "plain" -> no envelope (validated only; e.g. read by the TS runtime)
    kind: str
    payload_key: Optional[str] = None


ARTIFACTS: Dict[str, ArtifactSpec] = {
    s.name: s for s in [
        ArtifactSpec("dom_elements", m.DomElementsV2, "dom_elements.json", "dict"),
        ArtifactSpec("business_scenarios", m.BusinessScenariosV2, "business_scenarios.json", "dict"),
        ArtifactSpec("test_data", m.TestDataV2, "test_data.json", "list", "datasets"),
        ArtifactSpec("scenario_element_map", m.ScenarioElementMapV2, "scenario_element_map.json", "map", "scenarios"),
        ArtifactSpec("test_plans", m.TestPlansV2, "test_plans.json", "map", "plans"),
        ArtifactSpec("test_suite", m.TestSuiteV2, "test_suite.json", "dict"),
        ArtifactSpec("execution_results", m.ExecutionResultsV2, "execution_results.json", "dict"),
        ArtifactSpec("playwright_report", m.PlaywrightReportLoose, "_results.json", "plain"),
        ArtifactSpec("locator_map", m.LocatorEntry, "locator_map.json", "plain"),
        ArtifactSpec("requirements", m.RequirementsV2, "requirements.json", "dict"),
        ArtifactSpec("traceability", m.TraceabilityV2, "traceability.json", "dict"),
        ArtifactSpec("test_cases", m.TestCasesV2, "test_cases.json", "dict"),
        ArtifactSpec("app_map", m.AppMapV2, "app_map.json", "dict"),
        ArtifactSpec("form_model", m.FormModelV2, "form_model.json", "dict"),
        ArtifactSpec("api_inventory", m.ApiInventoryV2, "api_inventory.json", "dict"),
        ArtifactSpec("permission_matrix", m.PermissionMatrixV2, "permission_matrix.json", "dict"),
        ArtifactSpec("baseline", m.BaselineV2, "baseline.json", "dict"),
    ]
}

# Artifacts that carry a schema_version envelope (everything except "plain").
VERSIONED = tuple(n for n, s in ARTIFACTS.items() if s.kind != "plain")


def spec_for(name: str) -> ArtifactSpec:
    try:
        return ARTIFACTS[name]
    except KeyError:
        raise KeyError(f"unknown artifact '{name}' (known: {sorted(ARTIFACTS)})") from None
