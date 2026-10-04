import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.comprehension.discovery.agent import DiscoveryAgent


def _intent(intent_id, name="click_thing", locator_id="LOC-0001"):
    return {
        "intent_id": intent_id,
        "intent_name": name,
        "action": "click",
        "locator_id": locator_id,
        "value": None,
        "expected_result": None,
    }


class IntentsYamlMergeTests(unittest.TestCase):
    """intents.yaml must accumulate across modules (each module_id's slice
    replaced independently), not get wholesale-overwritten by whichever
    module was scanned most recently — the exact bug found in AWS_Test,
    where a 4-module project's intents.yaml only ever reflected M01."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        p = patch("agents.comprehension.discovery.agent._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)
        self.agent = DiscoveryAgent()

    def _read_intents_yaml(self, project="proj"):
        path = os.path.join(self.tmp_dir, project, "test_creation", "intents.yaml")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_second_module_does_not_wipe_first_modules_intents(self):
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "click_products")],
            safe="proj", project_name="proj", module_id="M01",
        )
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "click_pricing_tier")],
            safe="proj", project_name="proj", module_id="M02",
        )

        data = self._read_intents_yaml()
        by_module = {(i["module_id"], i["intent_id"]): i for i in data["intents"]}
        self.assertEqual(len(data["intents"]), 2)
        self.assertIn(("M01", "DOM_INT_001"), by_module)
        self.assertIn(("M02", "DOM_INT_001"), by_module)
        self.assertEqual(by_module[("M01", "DOM_INT_001")]["intent_name"], "click_products")
        self.assertEqual(by_module[("M02", "DOM_INT_001")]["intent_name"], "click_pricing_tier")

    def test_rescanning_a_module_only_replaces_that_modules_slice(self):
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "click_products")],
            safe="proj", project_name="proj", module_id="M01",
        )
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "click_pricing_tier")],
            safe="proj", project_name="proj", module_id="M02",
        )
        # Re-scan M01 with a changed intent set
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "click_products_v2"),
                         _intent("DOM_INT_002", "click_solutions")],
            safe="proj", project_name="proj", module_id="M01",
        )

        data = self._read_intents_yaml()
        m01 = [i for i in data["intents"] if i["module_id"] == "M01"]
        m02 = [i for i in data["intents"] if i["module_id"] == "M02"]
        self.assertEqual(len(m01), 2)
        self.assertEqual(len(m02), 1)
        self.assertEqual(m02[0]["intent_name"], "click_pricing_tier")

    def test_scenario_mapped_module_slice_is_preserved_not_reset(self):
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "click_products")],
            safe="proj", project_name="proj", module_id="M01",
        )
        # Simulate SemanticMapAgent having populated source_scenarios for M01
        path = os.path.join(self.tmp_dir, "proj", "test_creation", "intents.yaml")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data["intents"][0]["source_scenarios"] = ["M01_BS_001"]
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        # A later rescan of M01 must not wipe that mapping back to []
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "click_products")],
            safe="proj", project_name="proj", module_id="M01",
        )

        result = self._read_intents_yaml()
        self.assertEqual(result["intents"][0]["source_scenarios"], ["M01_BS_001"])

    def test_legacy_module_id_less_entries_are_superseded_not_duplicated(self):
        # Simulate a pre-existing intents.yaml written by the old
        # wholesale-overwrite implementation, before module_id tagging
        # existed (the exact real-world AWS_Test state this fix migrates).
        tc_dir = os.path.join(self.tmp_dir, "proj", "test_creation")
        os.makedirs(tc_dir, exist_ok=True)
        with open(os.path.join(tc_dir, "intents.yaml"), "w", encoding="utf-8") as f:
            yaml.dump({
                "project": "proj",
                "intents": [
                    {"intent_id": "DOM_INT_001", "intent_name": "enter_element",
                     "action": "fill", "locator_id": "LOC-0001",
                     "value": None, "expected_result": None, "source_scenarios": []},
                ],
            }, f)

        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001", "enter_element")],
            safe="proj", project_name="proj", module_id="M01",
        )

        data = self._read_intents_yaml()
        self.assertEqual(len(data["intents"]), 1, "legacy untagged entry must be replaced, not duplicated")
        self.assertEqual(data["intents"][0]["module_id"], "M01")

    def test_non_modular_project_still_writes_module_id_none(self):
        self.agent._save_intents_yaml(
            dom_intents=[_intent("DOM_INT_001")],
            safe="proj", project_name="proj", module_id=None,
        )
        data = self._read_intents_yaml()
        self.assertEqual(data["intents"][0]["module_id"], None)


if __name__ == "__main__":
    unittest.main()
