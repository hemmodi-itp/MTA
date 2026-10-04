import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_creation.testdata.models import NegativeVariant, TestDataIteration, TestDataField


def _field(name="email", value="bad"):
    return {"field_name": name, "field_type": "email", "value": value}


class NegativeVariantIterationsTests(unittest.TestCase):
    def test_new_shape_with_iterations_loads_directly(self):
        variant = NegativeVariant.model_validate({
            "variant_id": "NEG-001",
            "variant_type": "negative",
            "description": "Representative bad inputs",
            "iterations": [
                {"fields": [_field(value="")], "expected_error": "Email is required"},
                {"fields": [_field(value="not-an-email")], "expected_error": "Invalid email format"},
            ],
        })
        self.assertEqual(len(variant.iterations), 2)
        self.assertEqual(variant.iterations[0].expected_error, "Email is required")

    def test_legacy_flat_shape_migrates_to_single_iteration(self):
        variant = NegativeVariant.model_validate({
            "variant_id": "NEG-001",
            "variant_type": "empty",
            "description": "All fields blank",
            "fields": [_field(value="")],
            "expected_error": "Email is required",
        })
        self.assertEqual(len(variant.iterations), 1)
        self.assertEqual(variant.iterations[0].fields[0].value, "")
        self.assertEqual(variant.iterations[0].expected_error, "Email is required")

    def test_legacy_shape_without_expected_error_migrates_cleanly(self):
        variant = NegativeVariant.model_validate({
            "variant_id": "NEG-002",
            "variant_type": "boundary",
            "description": "At boundary",
            "fields": [_field(value="a" * 255)],
        })
        self.assertEqual(len(variant.iterations), 1)
        self.assertIsNone(variant.iterations[0].expected_error)

    def test_round_trip_dump_and_reload(self):
        original = NegativeVariant(
            variant_id="NEG-001",
            variant_type="negative",
            description="desc",
            iterations=[TestDataIteration(fields=[TestDataField(**_field())], expected_error="err")],
        )
        reloaded = NegativeVariant.model_validate(original.model_dump())
        self.assertEqual(reloaded, original)


if __name__ == "__main__":
    unittest.main()
