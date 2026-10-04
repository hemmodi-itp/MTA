from typing import List, Optional
from pydantic import BaseModel


class TestDataField(BaseModel):
    field_name: str
    field_type: str   # text | email | password | phone | number | select | date | textarea
    value: str


class NegativeVariant(BaseModel):
    variant_id: str        # NEG-001
    variant_type: str      # empty | special_chars | wrong_format | boundary | random
    description: str
    fields: List[TestDataField]
    expected_error: Optional[str] = None


class ScenarioTestData(BaseModel):
    testdata_id: str              # TD-001
    scenario_id: str              # BS-001  (traceability back to comprehension output)
    scenario_title: str
    actor: str
    positive_dataset: List[TestDataField]
    negative_variants: List[NegativeVariant]
