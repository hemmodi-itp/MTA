import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.test_creation.testdata.models import (
    NegativeVariant,
    ScenarioTestData,
    TestDataField,
    TestDataIteration,
)
from tools.test_creation.testdata.export_test_data import export_test_data


class ExportTestDataTests(unittest.TestCase):
    def test_writes_json_and_markdown_without_error(self):
        ds = ScenarioTestData(
            testdata_id="TD-001", scenario_id="M03_BS_001", scenario_title="Login", actor="User",
            positive_dataset=[TestDataField(field_name="email", field_type="email", value="a@b.com")],
            negative_variants=[
                NegativeVariant(
                    variant_id="NEG-001", variant_type="negative", description="Empty field",
                    iterations=[
                        TestDataIteration(
                            fields=[TestDataField(field_name="email", field_type="email", value="")],
                            expected_error="Email is required",
                        ),
                        TestDataIteration(
                            fields=[TestDataField(field_name="email", field_type="email", value="not-an-email")],
                            expected_error="Invalid email",
                        ),
                    ],
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = export_test_data([ds], tmp_dir, "proj")
            with open(paths["markdown"], encoding="utf-8") as f:
                md = f.read()

        self.assertIn("NEG-001", md)
        self.assertIn("Iteration 1", md)
        self.assertIn("Iteration 2", md)
        self.assertIn("Email is required", md)


if __name__ == "__main__":
    unittest.main()
