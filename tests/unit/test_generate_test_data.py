import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.comprehension.models import BusinessScenario
from tools.test_creation.testdata.generate_test_data import generate_test_data
from agents.test_creation.testdata.prompt import TEST_DATA_GENERATION_PROMPT


class _FakeLLM:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload)

    def generate(self, prompt: str) -> str:
        return self._payload


def _scenario():
    return BusinessScenario(
        scenario_id="M03_BS_001",
        title="Login",
        business_objective="Verify login",
        actor="User",
        preconditions=[],
        steps=["User enters email", "User enters password"],
        expected_result="User is logged in",
    )


def _variant(variant_type, n_iterations=1):
    return {
        "variant_type": variant_type,
        "description": f"{variant_type} case",
        "iterations": [
            {"fields": [{"field_name": "email", "field_type": "email", "value": f"bad{i}"}],
             "expected_error": f"error {i}"}
            for i in range(n_iterations)
        ],
    }


class GenerateTestDataTests(unittest.TestCase):
    def test_defaults_cap_to_one_negative_one_boundary_three_iterations(self):
        llm = _FakeLLM({
            "positive_dataset": [{"field_name": "email", "field_type": "email", "value": "a@b.com"}],
            "negative_variants": [
                _variant("negative", n_iterations=5),
                _variant("negative", n_iterations=1),  # a 2nd negative variant — should be dropped
                _variant("boundary", n_iterations=5),
            ],
        })
        result = generate_test_data(
            scenario=_scenario(), llm_connector=llm, prompt_template=TEST_DATA_GENERATION_PROMPT,
            skill_header="", testdata_index=1,
        )
        negatives = [v for v in result.negative_variants if v.variant_type == "negative"]
        boundaries = [v for v in result.negative_variants if v.variant_type == "boundary"]

        self.assertEqual(len(negatives), 1)
        self.assertEqual(len(boundaries), 1)
        self.assertEqual(len(negatives[0].iterations), 3)   # capped from 5
        self.assertEqual(len(boundaries[0].iterations), 3)  # capped from 5

    def test_custom_limits_are_respected(self):
        llm = _FakeLLM({
            "positive_dataset": [{"field_name": "email", "field_type": "email", "value": "a@b.com"}],
            "negative_variants": [
                _variant("negative", n_iterations=5),
                _variant("negative", n_iterations=5),
                _variant("boundary", n_iterations=5),
            ],
        })
        result = generate_test_data(
            scenario=_scenario(), llm_connector=llm, prompt_template=TEST_DATA_GENERATION_PROMPT,
            skill_header="", testdata_index=1,
            max_negative_cases=2, max_boundary_cases=1, max_data_iterations=2,
        )
        negatives = [v for v in result.negative_variants if v.variant_type == "negative"]
        self.assertEqual(len(negatives), 2)
        self.assertEqual(len(negatives[0].iterations), 2)

    def test_prompt_contains_read_only_branch_instructions(self):
        rendered = TEST_DATA_GENERATION_PROMPT.safe_substitute(
            skill_header="", fill_fields_hint="", existing_format_guide="",
            scenario_id="BS-001", title="t", actor="User", business_objective="b",
            preconditions_json="[]", steps_json="[]", expected_result="e",
            max_negative_cases=1, max_boundary_cases=1, max_data_iterations=3,
        )
        self.assertIn("READ-ONLY", rendered)
        self.assertIn("navigation", rendered)
        self.assertIn("assertion", rendered)
        self.assertIn("count_min", rendered)

    def test_read_only_scenario_assertion_fields_parse_correctly(self):
        """A read-only scenario's LLM response uses navigation/assertion field
        types instead of form-input types — must still parse into a valid
        ScenarioTestData with a non-empty positive_dataset (the old prompt's
        taxonomy this restores; previously these scenarios got nothing)."""
        read_only_scenario = BusinessScenario(
            scenario_id="M03_BS_002",
            title="View dashboard",
            business_objective="Verify dashboard renders",
            actor="User",
            preconditions=[],
            steps=["User views the dashboard", "User scrolls to the summary section"],
            expected_result="Summary section is visible with at least 3 items",
        )
        llm = _FakeLLM({
            "positive_dataset": [
                {"field_name": "scroll_target", "field_type": "navigation", "value": "summary_section"},
                {"field_name": "expected_heading", "field_type": "assertion", "value": "Summary"},
                {"field_name": "min_items_count", "field_type": "count_min", "value": "3"},
            ],
            "negative_variants": [
                {
                    "variant_type": "negative",
                    "description": "Summary section missing",
                    "iterations": [
                        {
                            "fields": [
                                {"field_name": "expected_heading", "field_type": "assertion", "value": ""}
                            ],
                            "expected_error": "Expected heading not found on page",
                        }
                    ],
                },
            ],
        })
        result = generate_test_data(
            scenario=read_only_scenario, llm_connector=llm, prompt_template=TEST_DATA_GENERATION_PROMPT,
            skill_header="", testdata_index=2,
        )
        self.assertEqual(len(result.positive_dataset), 3)
        self.assertEqual(len(result.negative_variants), 1)
        self.assertEqual(result.negative_variants[0].variant_type, "negative")

    def test_legacy_flat_llm_output_still_parses(self):
        llm = _FakeLLM({
            "positive_dataset": [{"field_name": "email", "field_type": "email", "value": "a@b.com"}],
            "negative_variants": [
                {
                    "variant_type": "negative",
                    "description": "empty field",
                    "fields": [{"field_name": "email", "field_type": "email", "value": ""}],
                    "expected_error": "Email is required",
                },
            ],
        })
        result = generate_test_data(
            scenario=_scenario(), llm_connector=llm, prompt_template=TEST_DATA_GENERATION_PROMPT,
            skill_header="", testdata_index=1,
        )
        self.assertEqual(len(result.negative_variants), 1)
        self.assertEqual(result.negative_variants[0].iterations[0].expected_error, "Email is required")


if __name__ == "__main__":
    unittest.main()
