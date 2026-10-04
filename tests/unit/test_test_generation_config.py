import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import tools.config.test_generation_config as tgc


class LoadTestGenerationConfigTests(unittest.TestCase):
    def test_defaults_when_no_project_yaml(self):
        with patch("os.path.exists", return_value=False):
            config = tgc.load_test_generation_config("nonexistent_project")
        self.assertEqual(config, tgc.DEFAULT_TEST_GENERATION_CONFIG)

    def test_project_level_override_applies(self):
        cfg_yaml = {"test_generation": {"max_negative_cases": 2, "max_data_iterations": 5}}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open"), \
             patch("yaml.safe_load", return_value=cfg_yaml):
            config = tgc.load_test_generation_config("proj")
        self.assertEqual(config["max_negative_cases"], 2)
        self.assertEqual(config["max_data_iterations"], 5)
        self.assertEqual(config["max_boundary_cases"], 1)  # untouched default

    def test_module_level_override_wins_over_project_level(self):
        cfg_yaml = {
            "test_generation": {"max_negative_cases": 2},
            "modules": [
                {"id": "M01", "test_generation": {"max_negative_cases": 3}},
                {"id": "M03", "test_generation": {"max_boundary_cases": 4}},
            ],
        }
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open"), \
             patch("yaml.safe_load", return_value=cfg_yaml):
            m01_config = tgc.load_test_generation_config("proj", module_id="M01")
            m03_config = tgc.load_test_generation_config("proj", module_id="M03")

        self.assertEqual(m01_config["max_negative_cases"], 3)
        self.assertEqual(m03_config["max_negative_cases"], 2)  # project-level, no M03 override
        self.assertEqual(m03_config["max_boundary_cases"], 4)

    def test_unmatched_module_id_falls_back_to_project_level(self):
        cfg_yaml = {"test_generation": {"max_negative_cases": 2}, "modules": [{"id": "M01"}]}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open"), \
             patch("yaml.safe_load", return_value=cfg_yaml):
            config = tgc.load_test_generation_config("proj", module_id="M99")
        self.assertEqual(config["max_negative_cases"], 2)

    def test_malformed_yaml_falls_back_to_defaults(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open"), \
             patch("yaml.safe_load", side_effect=Exception("bad yaml")):
            config = tgc.load_test_generation_config("proj")
        self.assertEqual(config, tgc.DEFAULT_TEST_GENERATION_CONFIG)

    def test_non_numeric_override_is_ignored(self):
        cfg_yaml = {"test_generation": {"max_negative_cases": "not_a_number"}}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open"), \
             patch("yaml.safe_load", return_value=cfg_yaml):
            config = tgc.load_test_generation_config("proj")
        self.assertEqual(config["max_negative_cases"], 1)


if __name__ == "__main__":
    unittest.main()
