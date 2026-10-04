import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from tools.comprehension.generate_business_scenarios import generate_business_scenarios
from tools.state.artifact_registry import ArtifactRegistry


class _FakeLLM:
    """Returns a fixed set of scenarios, capturing the prompt for inspection."""

    def __init__(self, scenarios):
        self._payload = json.dumps({"scenarios": scenarios})
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self._payload


def _scenario_payload(title, scenario_id="BS-001"):
    return {
        "scenario_id": scenario_id,
        "title": title,
        "business_objective": f"Verify {title}",
        "actor": "User",
        "preconditions": [],
        "steps": [f"Do {title}"],
        "expected_result": f"{title} succeeds",
        "business_rules": [],
        "traceability": [],
        "confidence_score": 0.9,
    }


class GenerateBusinessScenariosRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.registry = ArtifactRegistry(self.tmp_dir)

    def test_ids_are_module_prefixed_when_registry_provided(self):
        llm = _FakeLLM([_scenario_payload("Dashboard loads widgets")])
        scenarios = generate_business_scenarios(
            project_name="proj",
            requirements=[],
            business_rules=[],
            actors=[],
            workflows=[],
            llm_provider=llm,
            module_id="M03",
            module_name="Dashboard",
            registry=self.registry,
        )
        self.assertEqual(scenarios[0].scenario_id, "M03_BS_001")
        self.assertIsNotNone(scenarios[0].content_hash)

    def test_two_modules_with_identically_worded_llm_output_do_not_collide(self):
        # Simulates the reported bug: the LLM is told to restart numbering at
        # BS-001 for every module call. Without the registry this collides;
        # with it, each module gets its own non-overlapping ID space.
        llm_m01 = _FakeLLM([_scenario_payload("Login with valid credentials", "BS-001")])
        llm_m03 = _FakeLLM([_scenario_payload("Dashboard loads widgets", "BS-001")])

        m01_scenarios = generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm_m01, module_id="M01", module_name="Login", registry=self.registry,
        )
        m03_scenarios = generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm_m03, module_id="M03", module_name="Dashboard", registry=self.registry,
        )

        self.assertEqual(m01_scenarios[0].scenario_id, "M01_BS_001")
        self.assertEqual(m03_scenarios[0].scenario_id, "M03_BS_001")
        self.assertNotEqual(m01_scenarios[0].scenario_id, m03_scenarios[0].scenario_id)

    def test_rerunning_same_module_with_unchanged_content_reuses_id(self):
        llm = _FakeLLM([_scenario_payload("Dashboard loads widgets")])
        first_run = generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm, module_id="M03", module_name="Dashboard", registry=self.registry,
        )
        second_run = generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm, module_id="M03", module_name="Dashboard", registry=self.registry,
        )
        self.assertEqual(first_run[0].scenario_id, second_run[0].scenario_id)

    def test_new_scenario_added_to_module_gets_a_fresh_id_not_a_collision(self):
        llm_first = _FakeLLM([_scenario_payload("Dashboard loads widgets")])
        generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm_first, module_id="M03", module_name="Dashboard", registry=self.registry,
        )

        # Re-uploaded BRD adds a brand new scenario for the same module.
        llm_second = _FakeLLM([
            _scenario_payload("Dashboard loads widgets"),
            _scenario_payload("Dashboard filters by date range", "BS-001"),
        ])
        second_run = generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm_second, module_id="M03", module_name="Dashboard", registry=self.registry,
        )

        ids = [s.scenario_id for s in second_run]
        self.assertEqual(ids, ["M03_BS_001", "M03_BS_002"])

    def test_without_registry_falls_back_to_legacy_enumerate_behaviour(self):
        payload = _scenario_payload("Dashboard loads widgets")
        del payload["scenario_id"]  # simulate the LLM omitting the field entirely
        llm = _FakeLLM([payload])
        scenarios = generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm, module_id="M03", module_name="Dashboard",
        )
        self.assertEqual(scenarios[0].scenario_id, "BS-001")


class ExistingScenariosPromptContextTests(unittest.TestCase):
    def test_existing_scenarios_are_rendered_into_the_prompt(self):
        llm = _FakeLLM([_scenario_payload("New scenario")])
        generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm,
            existing_scenarios=[{"scenario_id": "M01_BS_001", "title": "Login with valid credentials"}],
        )
        self.assertIn("M01_BS_001", llm.last_prompt)
        self.assertIn("Login with valid credentials", llm.last_prompt)
        self.assertIn("Already Covered", llm.last_prompt)

    def test_no_existing_scenarios_renders_empty_list_not_missing_placeholder(self):
        llm = _FakeLLM([_scenario_payload("New scenario")])
        generate_business_scenarios(
            project_name="proj", requirements=[], business_rules=[], actors=[], workflows=[],
            llm_provider=llm,
        )
        self.assertIn("[]", llm.last_prompt)
        self.assertNotIn("$existing_scenarios_json", llm.last_prompt)


if __name__ == "__main__":
    unittest.main()
