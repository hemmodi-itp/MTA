import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_creation.testdata.models import (
    NegativeVariant,
    ScenarioTestData,
    TestDataField,
    TestDataIteration,
)
from tools.test_creation.testdata.validate_test_data import validate_test_data


def _positive():
    return [TestDataField(field_name="email", field_type="email", value="a@b.com")]


def _variant(variant_type="negative", n_fields=1):
    fields = [TestDataField(field_name="email", field_type="email", value="bad")] if n_fields else []
    return NegativeVariant(
        variant_id="NEG-001",
        variant_type=variant_type,
        description="desc",
        iterations=[TestDataIteration(fields=fields, expected_error="err")],
    )


class ValidateTestDataTests(unittest.TestCase):
    def test_single_negative_and_boundary_variant_is_valid(self):
        ds = ScenarioTestData(
            testdata_id="TD-001", scenario_id="M03_BS_001", scenario_title="t", actor="User",
            positive_dataset=_positive(),
            negative_variants=[_variant("negative"), _variant("boundary")],
        )
        valid, warnings = validate_test_data([ds])
        self.assertEqual(valid, [ds])
        self.assertEqual(warnings, [])

    def test_no_longer_requires_three_variants(self):
        # This is the exact case the old _MIN_VARIANTS=3 gate used to reject.
        ds = ScenarioTestData(
            testdata_id="TD-001", scenario_id="M03_BS_001", scenario_title="t", actor="User",
            positive_dataset=_positive(),
            negative_variants=[_variant("negative")],
        )
        valid, warnings = validate_test_data([ds])
        self.assertEqual(valid, [ds])
        self.assertEqual(warnings, [])

    def test_read_only_scenario_with_no_fields_is_valid(self):
        ds = ScenarioTestData(
            testdata_id="TD-001", scenario_id="M03_BS_002", scenario_title="t", actor="User",
            positive_dataset=[], negative_variants=[],
        )
        valid, warnings = validate_test_data([ds])
        self.assertEqual(valid, [ds])

    def test_missing_positive_dataset_is_a_hard_failure(self):
        ds = ScenarioTestData(
            testdata_id="TD-001", scenario_id="M03_BS_001", scenario_title="t", actor="User",
            positive_dataset=[], negative_variants=[_variant("negative")],
        )
        valid, warnings = validate_test_data([ds])
        self.assertEqual(valid, [])
        self.assertTrue(any("no positive dataset fields" in w for w in warnings))

    def test_variant_with_no_usable_iterations_is_a_hard_failure(self):
        ds = ScenarioTestData(
            testdata_id="TD-001", scenario_id="M03_BS_001", scenario_title="t", actor="User",
            positive_dataset=_positive(),
            negative_variants=[_variant("negative", n_fields=0)],
        )
        valid, warnings = validate_test_data([ds])
        self.assertEqual(valid, [])
        self.assertTrue(any("no usable iterations" in w for w in warnings))

    def test_unexpected_variant_type_is_a_soft_warning_only(self):
        ds = ScenarioTestData(
            testdata_id="TD-001", scenario_id="M03_BS_001", scenario_title="t", actor="User",
            positive_dataset=_positive(),
            negative_variants=[_variant("out_of_box")],
        )
        valid, warnings = validate_test_data([ds])
        self.assertEqual(valid, [ds])  # still valid — just a warning
        self.assertTrue(any("unexpected variant type" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
