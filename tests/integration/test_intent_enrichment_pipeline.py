"""
Integration test for the intent-enrichment pipeline: DiscoveryAgent's
intents.yaml writer -> SemanticMapAgent's clustering/confidence/backlink ->
ScriptGenerationAgent's plan validation + placeholder-negative-test drop.

Deterministic and offline — LLM calls are replaced with stub connectors (no
network, no API key required), so this runs as part of the normal fast test
loop rather than being gated behind live credentials like
tests/integration/test_healing_agent_live.py. What IS real: every non-LLM
code path (module-scoped file I/O, clustering/confidence scoring, plan
validation, spec rendering) runs for real, chained across all three agents,
against one throwaway temp project — this is what a unit test scoped to a
single function can't catch (e.g. a real key-name mismatch between what
SemanticMapAgent writes and what ScriptGenerationAgent reads).
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from agents.comprehension.discovery.agent import DiscoveryAgent
from agents.test_creation.script_generation.agent import ScriptGenerationAgent
from agents.test_creation.semantic_map.agent import SemanticMapAgent


def _dom_element(locator_id, placeholder=None, role=None, role_name=None):
    pw = {}
    if placeholder:
        pw["get_by_placeholder"] = {"placeholder": placeholder}
    if role:
        pw["get_by_role"] = {"role": role, "name": role_name} if role_name else {"role": role}
    return {
        "locator_id": locator_id,
        "tag": "input" if placeholder else "button",
        "display_text": role_name or placeholder or "",
        "semantic_locators": {"role": role, "label": None, "placeholder": placeholder},
        "attribute_locators": {"id": None, "name": None, "testid": None},
        "playwright_locators": pw,
        "technical_locators": {"css": "", "xpath": ""},
        "recommended_locator": {"type": "", "value": {}},
        "intent_hints": [],
    }


def _dom_intent(intent_id, name, locator_id, action="click", expected_result=None):
    return {
        "intent_id": intent_id, "intent_name": name, "action": action,
        "locator_id": locator_id, "value": None, "expected_result": expected_result,
    }


def _extract_json_after(prompt: str, marker: str):
    """Robustly pull the JSON blob that immediately follows `marker` in a
    prompt string, ignoring whatever free-text follows it (avoids needing a
    brittle end-of-block regex)."""
    idx = prompt.index(marker) + len(marker)
    return json.JSONDecoder().raw_decode(prompt[idx:].lstrip())[0]


class _SemanticMapStubLLM:
    """Maps M01_BS_001 to the login-cluster locators, mirroring what a real
    LLM pass would pick — the clustering/confidence/backlink logic downstream
    of this response is entirely real code, not stubbed."""

    def generate(self, prompt: str) -> str:
        return json.dumps({
            "M01_BS_001": {
                "scenario_title": "Test login functionality",
                "relevant_elements": [
                    {"locator_id": "LOC-0001", "playwright_expr": "page.getByPlaceholder('Username')",
                     "relevance": "username field"},
                    {"locator_id": "LOC-0002", "playwright_expr": "page.getByPlaceholder('Password')",
                     "relevance": "password field"},
                ],
            }
        })


class _ScriptGenerationStubLLM:
    """Reads the real 'Allowed locator keys' block ScriptGenerationAgent
    built from locator_map.json (so this test isn't hardcoding key names
    that a real run would compute independently) and returns one positive
    test covering all of them, plus one negative test with a fabricated
    empty-string-only assertion that _drop_placeholder_negative_tests should
    strip before rendering."""

    def generate(self, prompt: str) -> str:
        locators = _extract_json_after(
            prompt, '== Allowed locator keys for THIS scenario (use ONLY these in "locator_key") ==\n'
        )
        keys = [e["key"] for e in locators]
        self.last_keys = keys
        steps = [{"action": "navigate"}]
        for k in keys:
            steps.append({"action": "enterText", "locator_key": k, "value": "someone"})
        steps.append({"action": "verifyUrl", "value": "/dashboard", "message": "lands on dashboard after login"})

        plan = {
            "tests": [
                {"name": "positive — login with valid credentials succeeds", "type": "positive", "steps": steps},
                {
                    "name": "negative — fabricated placeholder assertion",
                    "type": "negative",
                    "steps": [
                        {"action": "verifyText", "locator_key": keys[0], "value": "",
                         "message": "heading should be empty indicating failed load"},
                    ],
                },
            ],
            "missing_actions": [],
            "missing_locators": [],
        }
        return json.dumps(plan)


class IntentEnrichmentPipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.project = "proj"

        for target in (
            "agents.comprehension.discovery.agent._ASSETS_BASE",
            "agents.test_creation.semantic_map.agent._ASSETS_BASE",
            "agents.test_creation.script_generation.agent._ASSETS_BASE",
            "tools.discovery.dom_intents._ASSETS_BASE",
        ):
            p = patch(target, self.tmp_dir)
            p.start()
            self.addCleanup(p.stop)

        self._write_fixtures()

    def _write_fixtures(self):
        comp_dir = os.path.join(self.tmp_dir, self.project, "test_comprehension")
        module_dir = os.path.join(comp_dir, "modules", "M01")
        os.makedirs(module_dir, exist_ok=True)

        with open(os.path.join(module_dir, "dom_elements.json"), "w", encoding="utf-8") as f:
            json.dump({"url": "https://x", "project": self.project, "elements": [
                _dom_element("LOC-0001", placeholder="Username"),
                _dom_element("LOC-0002", placeholder="Password"),
            ]}, f)

        with open(os.path.join(module_dir, "dom_intents.json"), "w", encoding="utf-8") as f:
            json.dump({"intents": [
                _dom_intent("DOM_INT_001", "enter_username", "LOC-0001", action="fill"),
                _dom_intent("DOM_INT_002", "enter_password", "LOC-0002", action="fill"),
                # Bridge intents (not directly surfaced by the stub LLM as
                # "relevant", but present in the module's full intent list) —
                # "forgot_password"/"forgot_username" share the "forgot"
                # token with each other and "password"/"username" with the
                # two fields above, connecting all four into one login
                # cluster. This is what proves clustering pulls in the whole
                # functional bucket, not just what one LLM pass named.
                _dom_intent("DOM_INT_003", "click_forgot_password", "LOC-0003"),
                _dom_intent("DOM_INT_004", "click_forgot_username", "LOC-0004"),
            ]}, f)

        with open(os.path.join(comp_dir, "business_scenarios.json"), "w", encoding="utf-8") as f:
            json.dump({"scenarios": [{
                "scenario_id": "M01_BS_001",
                "title": "Test login functionality",
                "business_objective": "User logs in with username and password",
                "actor": "Registered user",
                "steps": ["Enter username", "Enter password", "Submit"],
                "expected_result": "User reaches the dashboard",
                "traceability": [],
                "module_id": "M01",
                "module_name": "Login",
            }]}, f)

    def test_full_chain_produces_enriched_map_and_drops_fabricated_negative_test(self):
        # ── Step 1: DiscoveryAgent writes intents.yaml (real code) ──
        discovery = DiscoveryAgent()
        with open(os.path.join(self.tmp_dir, self.project, "test_comprehension", "modules", "M01",
                                "dom_intents.json"), encoding="utf-8") as f:
            dom_intents = json.load(f)["intents"]
        discovery._save_intents_yaml(
            dom_intents=dom_intents, safe=self.project, project_name=self.project,
            source="ui_scanner", module_id="M01",
        )

        # ── Step 2: SemanticMapAgent maps + clusters + backlinks (real code, stub LLM) ──
        semantic = SemanticMapAgent(settings={})
        semantic.registry.get_llm = MagicMock(return_value=_SemanticMapStubLLM())
        sm_result = semantic.execute({"project_name": self.project, "module_filter": "M01"}, {})
        self.assertEqual(sm_result["status"], "success")

        tc_dir = os.path.join(self.tmp_dir, self.project, "test_creation")
        with open(os.path.join(tc_dir, "scenario_element_map.json"), encoding="utf-8") as f:
            scenario_map = json.load(f)
        elements = scenario_map["M01_BS_001"]["relevant_elements"]
        self.assertEqual(len(elements), 2)
        for el in elements:
            self.assertIn("intent_id", el)
            self.assertIn("cluster", el)
            self.assertIsNotNone(el["confidence"])
        # username/password share tokens -> same cluster (functional bucket)
        self.assertEqual(elements[0]["cluster"], elements[1]["cluster"])

        with open(os.path.join(tc_dir, "intents.yaml"), encoding="utf-8") as f:
            intents_yaml = yaml.safe_load(f)
        backlinked = {i["intent_id"]: i["source_scenarios"] for i in intents_yaml["intents"]}
        self.assertEqual(backlinked["DOM_INT_001"], ["M01_BS_001"])
        self.assertEqual(backlinked["DOM_INT_002"], ["M01_BS_001"])

        # ── Step 3: ScriptGenerationAgent renders a spec (real code, stub LLM) ──
        script_gen = ScriptGenerationAgent(settings={})
        stub_llm = _ScriptGenerationStubLLM()
        script_gen._registry.get_llm = MagicMock(return_value=stub_llm)
        # Live locator validation needs a real reachable page — out of scope
        # here (covered by tests/unit/test_script_generation_locator_gate.py
        # and test_script_generation_locator_validation.py); this test's
        # target is the clustering/confidence/backlink + placeholder-drop
        # wiring, not Playwright's live-resolution behavior.
        script_gen._validate_locator_map_live = MagicMock(return_value=set())
        sg_result = script_gen.execute(
            {"project_name": self.project, "module_filter": "M01",
             "modules": [{"id": "M01", "name": "Login"}]},
            {},
        )
        self.assertIn(sg_result["status"], ("success", "partial"))
        self.assertEqual(sg_result["scripts_generated"], 1)

        spec_dir = os.path.join(tc_dir, "test_scripts", "M01")
        spec_files = os.listdir(spec_dir)
        self.assertEqual(len(spec_files), 1)
        with open(os.path.join(spec_dir, spec_files[0]), encoding="utf-8") as f:
            spec_content = f.read()

        # The real locator keys the stub discovered from the prompt must be
        # the ones actually rendered into the spec.
        self.assertEqual(len(stub_llm.last_keys), 2)
        for key in stub_llm.last_keys:
            self.assertIn(key, spec_content)

        # The fabricated negative test must NOT have been rendered.
        self.assertNotIn("fabricated placeholder assertion", spec_content)
        self.assertNotIn('"", "heading should be empty', spec_content)
        # The genuine positive test must have been rendered.
        self.assertIn("login with valid credentials succeeds", spec_content)


if __name__ == "__main__":
    unittest.main()
