import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.test_creation.semantic_map.agent import SemanticMapAgent


def _intent(intent_id, name, locator_id, action="click", expected_result=None):
    return {
        "intent_id": intent_id,
        "intent_name": name,
        "action": action,
        "locator_id": locator_id,
        "value": None,
        "expected_result": expected_result,
    }


class EnrichWithIntentsTests(unittest.TestCase):
    """SemanticMapAgent._enrich_with_intents is the bridge that gives
    scenario_element_map.json intent-level richness and closes the
    source_scenarios link back in intents.yaml — both previously broken
    (see docs/adk-unrelated plan notes: intents.yaml's source_scenarios was
    always [] because nothing in the active pipeline populated it)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        p = patch("agents.test_creation.semantic_map.agent._ASSETS_BASE", self.tmp_dir)
        p.start()
        self.addCleanup(p.stop)
        p2 = patch("tools.discovery.dom_intents._ASSETS_BASE", self.tmp_dir)
        p2.start()
        self.addCleanup(p2.stop)
        self.agent = SemanticMapAgent()
        self.safe = "proj"

    def _dom_intents_path(self, module_id):
        comp_dir = os.path.join(self.tmp_dir, self.safe, "test_comprehension", "modules", module_id)
        os.makedirs(comp_dir, exist_ok=True)
        return os.path.join(comp_dir, "dom_intents.json"), comp_dir

    def _write_dom_intents(self, module_id, intents):
        path, comp_dir = self._dom_intents_path(module_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"intents": intents}, f)
        return comp_dir

    def _write_intents_yaml(self, entries):
        tc_dir = os.path.join(self.tmp_dir, self.safe, "test_creation")
        os.makedirs(tc_dir, exist_ok=True)
        path = os.path.join(tc_dir, "intents.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump({"project": self.safe, "intents": entries}, f)
        return path

    def test_enriches_relevant_elements_and_backlinks_intents_yaml(self):
        intents = [
            _intent("DOM_INT_001", "enter_username", "LOC-0001", action="fill",
                    expected_result="username_entered"),
            _intent("DOM_INT_002", "enter_password", "LOC-0002", action="fill"),
            _intent("DOM_INT_003", "click_forgot_password", "LOC-0003"),
        ]
        comp_dir = self._write_dom_intents("M01", intents)
        self._write_intents_yaml([
            {"intent_id": i["intent_id"], "module_id": "M01", "source_scenarios": []}
            for i in intents
        ])

        scenarios = [{
            "scenario_id": "M01_BS_001",
            "title": "Test login functionality",
            "business_objective": "User logs in with username and password",
            "steps": ["Enter username", "Enter password"],
            "traceability": [],
        }]
        scenario_map = {
            "M01_BS_001": {
                "scenario_title": "Test login functionality",
                "relevant_elements": [
                    {"locator_id": "LOC-0001", "playwright_expr": "x", "relevance": "username field"},
                ],
            }
        }

        result = self.agent._enrich_with_intents(
            scenario_map, scenarios, self.safe, "M01",
            os.path.join(self.tmp_dir, self.safe, "test_comprehension"),
        )

        enriched = result["M01_BS_001"]["relevant_elements"][0]
        self.assertEqual(enriched["intent_id"], "DOM_INT_001")
        self.assertEqual(enriched["action"], "fill")
        self.assertEqual(enriched["expected_result"], "username_entered")
        self.assertIn("cluster", enriched)
        self.assertIn("confidence", enriched)

        intents_yaml_path = os.path.join(self.tmp_dir, self.safe, "test_creation", "intents.yaml")
        with open(intents_yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        matched = next(i for i in data["intents"] if i["intent_id"] == "DOM_INT_001")
        self.assertEqual(matched["source_scenarios"], ["M01_BS_001"])

    def test_no_dom_intents_is_a_graceful_noop(self):
        scenario_map = {"BS-001": {"relevant_elements": [{"locator_id": "LOC-0001"}]}}
        result = self.agent._enrich_with_intents(
            scenario_map, [{"scenario_id": "BS-001"}], self.safe, None,
            os.path.join(self.tmp_dir, self.safe, "test_comprehension"),
        )
        self.assertEqual(result, scenario_map)
        self.assertNotIn("intent_id", result["BS-001"]["relevant_elements"][0])

    def test_other_modules_intents_yaml_entries_are_untouched(self):
        self._write_dom_intents("M01", [_intent("DOM_INT_001", "click_products", "LOC-0001")])
        self._write_intents_yaml([
            {"intent_id": "DOM_INT_001", "module_id": "M01", "source_scenarios": []},
            {"intent_id": "DOM_INT_001", "module_id": "M02", "source_scenarios": ["M02_BS_005"]},
        ])
        scenario_map = {
            "M01_BS_001": {
                "relevant_elements": [{"locator_id": "LOC-0001"}],
            }
        }
        self.agent._enrich_with_intents(
            scenario_map, [{"scenario_id": "M01_BS_001", "title": "products", "steps": []}],
            self.safe, "M01", os.path.join(self.tmp_dir, self.safe, "test_comprehension"),
        )
        intents_yaml_path = os.path.join(self.tmp_dir, self.safe, "test_creation", "intents.yaml")
        with open(intents_yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        m02 = next(i for i in data["intents"] if i["module_id"] == "M02")
        self.assertEqual(m02["source_scenarios"], ["M02_BS_005"])


if __name__ == "__main__":
    unittest.main()
