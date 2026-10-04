from typing import Any, List, Optional
from pydantic import BaseModel, model_validator


class TestDataField(BaseModel):
    field_name: str
    field_type: str   # text | email | password | phone | number | select | date | textarea
    value: str


class TestDataIteration(BaseModel):
    """One alternate bad/boundary value set tried within a single variant.

    A variant (e.g. "negative") is allowed at most a handful of these —
    see test_generation.max_data_iterations in project.yaml — so a spec
    exercises a few representative bad inputs in one test() rather than one
    test() per input.
    """
    fields: List[TestDataField]
    expected_error: Optional[str] = None


class NegativeVariant(BaseModel):
    variant_id: str        # NEG-001
    variant_type: str      # negative | boundary (see test_generation config)
    description: str
    iterations: List[TestDataIteration]

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_flat_shape(cls, data: Any) -> Any:
        """Back-compat: older test_data.json records store a single
        fields/expected_error pair directly on the variant instead of an
        iterations list. Wrap them so old records still load."""
        if isinstance(data, dict) and "iterations" not in data and "fields" in data:
            data = dict(data)
            data["iterations"] = [
                {"fields": data.pop("fields", []), "expected_error": data.pop("expected_error", None)}
            ]
        return data


class ScenarioTestData(BaseModel):
    testdata_id: str              # TD-001
    scenario_id: str              # BS-001  (traceability back to comprehension output)
    scenario_title: str
    actor: str
    positive_dataset: List[TestDataField]
    negative_variants: List[NegativeVariant]
