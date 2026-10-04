from typing import List, Literal, Optional
from pydantic import BaseModel


class IntentDefinition(BaseModel):
    intent_id: str                       # INT-001
    intent_name: str                     # fill_email
    action: str                          # fill | click | select | navigate | verify
    locator_id: Optional[str] = None     # assigned by LocatorAgent later
    value: Optional[str] = None          # populated by enrich_with_testdata
    description: Optional[str] = None
    source_scenarios: List[str] = []     # BS-XXX ids that use this intent


class TestCase(BaseModel):
    test_case_id: str                    # TC-001
    test_case_name: str
    business_scenario_id: str            # BS-XXX
    steps: List[str]                     # ordered [INT-001, INT-002, ...]
    test_data_ref: Optional[str] = None  # TD-XXX
    expected_result: Optional[str] = None
    test_case_type: Literal["positive", "negative", "boundary", "out_of_box"] = "positive"


class TestSuiteDefinition(BaseModel):
    suite_name: str
    project: str
    test_cases: List[TestCase]
