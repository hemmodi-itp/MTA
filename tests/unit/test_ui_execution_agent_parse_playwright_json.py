import json
import logging
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_execution.ui_execution.agent import _parse_playwright_json

_FIXTURE = {
    "suites": [
        {
            "specs": [
                {
                    "file": "M02/test_BS-007_search.spec.ts",
                    "title": "search",
                    "tests": [
                        {
                            "status": "passed",
                            "duration": 500,
                            "results": [{"duration": 500}],
                        }
                    ],
                },
                {
                    "file": "M02/test_BS-011_filter.spec.ts",
                    "title": "filter",
                    "tests": [
                        {
                            "status": "failed",
                            "duration": 300,
                            "results": [
                                {"duration": 300, "error": {"message": "Timeout waiting for locator"}}
                            ],
                        }
                    ],
                },
            ]
        }
    ]
}


class ParsePlaywrightJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.json_path = os.path.join(self.tmp_dir, "results.json")
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(_FIXTURE, f)
        self.logger = logging.getLogger("test")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_test_case_id_and_business_scenario_id_derived_from_spec_file(self):
        results, passed, failed = _parse_playwright_json(self.json_path, self.logger)

        self.assertEqual(passed, 1)
        self.assertEqual(failed, 1)

        by_title = {r["test_title"]: r for r in results}
        self.assertEqual(by_title["search"]["test_case_id"], "BS-007")
        self.assertEqual(by_title["search"]["business_scenario_id"], "BS-007")
        self.assertEqual(by_title["search"]["status"], "success")

        self.assertEqual(by_title["filter"]["test_case_id"], "BS-011")
        self.assertEqual(by_title["filter"]["business_scenario_id"], "BS-011")
        self.assertEqual(by_title["filter"]["status"], "failed")
        self.assertIn("Timeout waiting for locator", by_title["filter"]["errors"])

    def test_module_scoped_underscore_id_is_extracted(self):
        fixture = {
            "suites": [{
                "specs": [{
                    "file": "M03/test_M03_BS_006_verify_page_title.spec.ts",
                    "title": "verify page title",
                    "tests": [{"status": "passed", "duration": 100, "results": [{"duration": 100}]}],
                }]
            }]
        }
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(fixture, f)

        results, _, _ = _parse_playwright_json(self.json_path, self.logger)
        self.assertEqual(results[0]["test_case_id"], "M03_BS_006")
        self.assertEqual(results[0]["business_scenario_id"], "M03_BS_006")

    def test_flaky_status_counts_as_passed_not_failed(self):
        # The real geminiTest bug: a test that failed its first attempt but
        # passed on Playwright's automatic retry gets status "flaky" in the
        # JSON reporter — Playwright's own summary counts this as a pass
        # (its "N flaky" bucket is separate from "N failed"), but the old
        # `status in ("passed", "expected")` check silently dropped "flaky"
        # into the failed bucket, undercounting real successes.
        fixture = {
            "suites": [{
                "specs": [{
                    "file": "M01/test_M01_BS_011_model_select.spec.ts",
                    "title": "model select",
                    "tests": [{
                        "status": "flaky",
                        "duration": 400,
                        "results": [
                            {"duration": 400, "error": {"message": "Timeout on first attempt"}},
                            {"duration": 200},
                        ],
                    }],
                }]
            }]
        }
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(fixture, f)

        results, passed, failed = _parse_playwright_json(self.json_path, self.logger)
        self.assertEqual(passed, 1)
        self.assertEqual(failed, 0)
        self.assertEqual(results[0]["status"], "success")
        self.assertTrue(results[0]["flaky"])

    def test_non_flaky_success_is_not_tagged_flaky(self):
        results, _, _ = _parse_playwright_json(self.json_path, self.logger)
        by_title = {r["test_title"]: r for r in results}
        self.assertFalse(by_title["search"]["flaky"])

    def test_missing_spec_id_yields_empty_id(self):
        fixture = {
            "suites": [{
                "specs": [{
                    "file": "M02/test_login.spec.ts",
                    "title": "login",
                    "tests": [{"status": "passed", "duration": 100, "results": [{"duration": 100}]}],
                }]
            }]
        }
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(fixture, f)

        results, _, _ = _parse_playwright_json(self.json_path, self.logger)
        self.assertEqual(results[0]["test_case_id"], "")


if __name__ == "__main__":
    unittest.main()
