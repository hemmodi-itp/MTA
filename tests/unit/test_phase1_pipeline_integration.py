"""Phase 1 through the real agents (LLM stubbed): ComprehensionAgent writes requirements.json and links
scenarios; ScriptGenerationAgent emits AC-tagged tests and traceability.json; with requirements.enabled off
both behave exactly as before."""

import json
from unittest.mock import MagicMock, patch

import yaml

from contracts.artifacts import load_payload, save_artifact

BRD = """# Login BRD

### REQ-01 Authentication

Users must sign in before using the shop.

- AC-01.1: Given valid credentials, when the user submits the login form, then they land on the Products page.
- AC-01.2: Given a wrong password, when the user submits the login form, then the page shows exactly "Invalid username or password".
"""

REQ_JSON = {"requirements": [{"id": "REQ-01", "title": "Authentication", "acceptance_criteria": [
    {"id": "AC-01.1", "statement": "valid login", "testability": "ui", "testability_reason": "redirect visible",
     "priority": "P0", "risk_tags": ["auth"]},
    {"id": "AC-01.2", "statement": "wrong password", "testability": "ui", "testability_reason": "message",
     "priority": "P1", "risk_tags": ["auth"]}]}]}
LEGACY_JSON = {"requirements": [{"requirement_id": "REQ-001", "description": "Users sign in"}],
               "business_rules": [], "actors": [{"name": "Customer"}], "workflows": []}
SCEN_JSON = {"scenarios": [
    {"scenario_id": "BS-001", "title": "Successful login", "business_objective": "access the shop",
     "actor": "Customer", "preconditions": [], "steps": ["enter valid credentials", "submit"],
     "expected_result": "the Products page is shown", "ac_ids": ["AC-01.1", "AC-99.9"], "confidence_score": 0.9},
    {"scenario_id": "BS-002", "title": "Wrong password is rejected", "business_objective": "protect accounts",
     "actor": "Customer", "preconditions": [], "steps": ["enter a wrong password", "submit"],
     "expected_result": "Invalid username or password is shown", "confidence_score": 0.9},
]}


class RoutingLLM:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if "testable requirements and ATOMIC" in prompt:
            return json.dumps(REQ_JSON)
        if "Generate Business Scenarios" in prompt:
            return json.dumps(SCEN_JSON)
        return json.dumps(LEGACY_JSON)


def _comprehension_project(tmp_path, monkeypatch, enabled):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    monkeypatch.setattr("agents.comprehension.comprehension_agent.agent._ASSETS_BASE", str(tmp_path))
    proj = tmp_path / "shop"
    (proj / "inputs").mkdir(parents=True)
    (proj / "inputs" / "brd_M01.md").write_text(BRD, encoding="utf-8")
    (proj / "project.yaml").write_text(yaml.safe_dump({
        "project": {"name": "shop"}, "requirements": {"enabled": enabled},
        "modules": [{"id": "M01", "name": "Login", "url": "https://shop.test/login", "brd_file": "brd_M01.md"}]}),
        encoding="utf-8")
    return proj


def _run_comprehension(proj, enabled):
    from agents.comprehension.comprehension_agent.agent import ComprehensionAgent

    agent = ComprehensionAgent(settings={})
    llm = RoutingLLM()
    agent._registry.get_llm = MagicMock(return_value=llm)
    out = agent.execute({"project_name": "shop", "brd_dir": str(proj / "inputs"),
                         "requirements": {"enabled": enabled},
                         "modules": [{"id": "M01", "name": "Login", "brd_file": "brd_M01.md"}]}, {})
    return out, llm


def test_comprehension_writes_requirements_and_links_scenarios(tmp_path, monkeypatch):
    proj = _comprehension_project(tmp_path, monkeypatch, True)
    out, llm = _run_comprehension(proj, True)
    assert out["status"] == "success"
    assert out["requirements"]["M01"]["criteria"] == 2 and out["requirements"]["M01"]["status"] == "ok"
    req = load_payload("requirements", str(proj / "test_comprehension" / "requirements.json"))
    assert [a["id"] for a in req["requirements"][0]["acceptance_criteria"]] == ["AC-01.1", "AC-01.2"]
    assert req["modules"]["M01"]["brd_file"] == "brd_M01.md"
    scen = {s["title"]: s for s in load_payload("business_scenarios",
                                                str(proj / "test_comprehension" / "business_scenarios.json"))["scenarios"]}
    assert scen["Successful login"]["ac_ids"] == ["AC-01.1"]                    # unknown AC-99.9 dropped
    assert scen["Successful login"]["ac_link_source"] == "llm"
    assert scen["Wrong password is rejected"]["ac_ids"] == ["AC-01.2"]          # similarity backfill
    assert scen["Wrong password is rejected"]["ac_link_source"] == "similarity"
    scenario_prompt = next(p for p in llm.prompts if "Generate Business Scenarios" in p)
    assert "- AC-01.2: Given a wrong password" in scenario_prompt


def test_comprehension_unchanged_when_disabled(tmp_path, monkeypatch):
    proj = _comprehension_project(tmp_path, monkeypatch, False)
    out, llm = _run_comprehension(proj, False)
    assert out["status"] == "success" and "requirements" not in out
    assert not (proj / "test_comprehension" / "requirements.json").exists()
    assert not any("testable requirements and ATOMIC" in p for p in llm.prompts)
    scenario_prompt = next(p for p in llm.prompts if "Generate Business Scenarios" in p)
    assert "Acceptance criteria" not in scenario_prompt and "$acceptance_criteria_block" not in scenario_prompt
    raw = (proj / "test_comprehension" / "business_scenarios.json").read_text(encoding="utf-8")
    assert "ac_ids" not in raw and "ac_link_source" not in raw


def test_comprehension_survives_requirements_failure(tmp_path, monkeypatch):
    proj = _comprehension_project(tmp_path, monkeypatch, True)
    with patch("agents.comprehension.comprehension_agent.agent.extract_for_module",
               side_effect=RuntimeError("boom")):
        out, _ = _run_comprehension(proj, True)
    assert out["status"] == "success" and out["requirements"]["M01"]["status"] == "failed"


# ── script generation ────────────────────────────────────────────────────────

PLAN = {"tests": [
    {"name": "positive — valid login", "type": "positive", "ac_ids": ["AC-01.1"], "steps": [
        {"action": "navigate"}, {"action": "enterText", "locator_key": "username", "value": "alice"},
        {"action": "click", "locator_key": "login_button"},
        {"action": "verifyUrlContains", "value": "/products", "message": "lands on products"}]},
    {"name": "negative — wrong password", "type": "negative", "steps": [
        {"action": "navigate"}, {"action": "enterText", "locator_key": "password", "value": "nope"},
        {"action": "click", "locator_key": "login_button"},
        {"action": "verifyContainsText", "locator_key": "error", "value": "Invalid username or password",
         "message": "generic error"}]},
], "missing_actions": [], "missing_locators": []}
LOCATORS = {"username": {"type": "label", "locator": "Username"}, "password": {"type": "label", "locator": "Password"},
            "login_button": {"type": "role", "locator": "button", "name": "Sign in"},
            "error": {"type": "role", "locator": "alert"}}


class PlanLLM:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(PLAN)


def _scriptgen_project(tmp_path, monkeypatch, enabled):
    monkeypatch.setattr("agents.test_creation.script_generation.agent._ASSETS_BASE", str(tmp_path))
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    proj = tmp_path / "shop"
    (proj / "test_comprehension").mkdir(parents=True)
    (proj / "test_creation" / "test_data").mkdir(parents=True)
    (proj / "project.yaml").write_text(yaml.safe_dump({
        "project": {"name": "shop"}, "requirements": {"enabled": enabled},
        "modules": [{"id": "M01", "url": "https://shop.test/login"}]}), encoding="utf-8")
    sc = {"scenario_id": "M01_BS_001", "title": "Login", "module_id": "M01", "steps": ["log in"]}
    if enabled:
        sc["ac_ids"] = ["AC-01.1", "AC-01.2"]
    save_artifact("business_scenarios", str(proj / "test_comprehension" / "business_scenarios.json"),
                  {"project": "shop", "scenarios": [sc]})
    (proj / "test_creation" / "locator_map.json").write_text(json.dumps(
        {k: {**v, "_module_id": "M01", "_source_locator_id": f"LOC-{i}"} for i, (k, v) in enumerate(LOCATORS.items())}),
        encoding="utf-8")
    (proj / "test_creation" / "scenario_element_map.json").write_text(json.dumps({"M01_BS_001": {
        "relevant_elements": [{"locator_id": f"LOC-{i}"} for i in range(len(LOCATORS))]}}), encoding="utf-8")
    save_artifact("test_data", str(proj / "test_creation" / "test_data" / "test_data.json"), [
        {"testdata_id": "TD-001", "scenario_id": "M01_BS_001", "scenario_title": "Login", "actor": "Customer",
         "positive_dataset": [], "negative_variants": [{"variant_id": "NEG-001", "variant_type": "negative",
                                                        "description": "wrong password", "iterations": [
                                                            {"fields": [], "expected_error": "Invalid username or password"}]}]}])
    if enabled:
        from tools.requirements.models import RequirementsDoc
        doc = RequirementsDoc.model_validate({"project": "shop", "requirements": [
            {"id": "REQ-01", "title": "Authentication", "module_id": "M01", "acceptance_criteria": [
                {"id": "AC-01.1", "statement": "Given valid credentials the user lands on the Products page",
                 "testability": "ui", "testability_reason": "r", "priority": "P0", "risk_tags": ["auth"]},
                {"id": "AC-01.2", "statement": "a wrong password shows exactly Invalid username or password",
                 "testability": "ui", "testability_reason": "r", "priority": "P1", "risk_tags": ["auth"]}]}]})
        save_artifact("requirements", str(proj / "test_comprehension" / "requirements.json"),
                      doc.model_dump(mode="json"))
    return proj


def _run_scriptgen(tmp_path, monkeypatch, enabled):
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent

    proj = _scriptgen_project(tmp_path, monkeypatch, enabled)
    agent = ScriptGenerationAgent(settings={})
    llm = PlanLLM()
    agent._registry.get_llm = MagicMock(return_value=llm)
    with patch.object(ScriptGenerationAgent, "_validate_locator_map_live", return_value=set()), \
         patch("agents.test_creation.script_generation.agent.write_named_locator_map",
               return_value={"added": [], "updated": [], "possibly_removed": []}), \
         patch("agents.test_creation.script_generation.agent.update_catalog"):
        out = agent.execute({"project_name": "shop", "requirements": {"enabled": enabled},
                             "modules": [{"id": "M01", "url": "https://shop.test/login"}]}, {})
    spec = next((proj / "test_creation" / "test_scripts" / "M01").glob("*.spec.ts")).read_text(encoding="utf-8")
    return proj, out, spec, llm


def test_scriptgen_emits_tagged_tests_and_traceability(tmp_path, monkeypatch):
    proj, out, spec, llm = _run_scriptgen(tmp_path, monkeypatch, True)
    assert out["scripts_generated"] == 1
    assert "- AC-01.2: a wrong password shows exactly" in llm.prompts[0]
    assert ('test("AC-01.1 positive — valid login", { tag: ["@P0", "@positive", "@smoke", "@REQ-01", '
            '"@AC-01.1"], annotation: [{ type: "ac", description: "AC-01.1" }, { type: "tc", description: '
            '"M01_TC_001" }, { type: "scenario", description: "M01_BS_001" }] }, async ({ action }) => {') in spec
    assert 'test("AC-01.2 negative — wrong password", { tag: ["@P1", "@negative", "@regression"' in spec
    plans = load_payload("test_plans", str(proj / "test_creation" / "test_plans.json"))
    t1, t2 = plans["M01_BS_001"]["tests"]
    assert (t1["tc_id"], t1["ac_link"], t2["ac_link"]) == ("M01_TC_001", "direct", "similarity")
    trace = load_payload("traceability", str(proj / "test_creation" / "traceability.json"))
    assert trace["acs"]["AC-01.1"]["tc_ids"] == ["M01_TC_001"] and trace["acs"]["AC-01.2"]["status"] == "covered"
    assert trace["unlinked_tests"] == []
    assert trace["tests"]["M01_TC_002"]["test_title"] == "AC-01.2 negative — wrong password"


def test_scriptgen_unchanged_when_disabled(tmp_path, monkeypatch):
    proj, out, spec, llm = _run_scriptgen(tmp_path, monkeypatch, False)
    assert out["scripts_generated"] == 1
    assert "Acceptance criteria" not in llm.prompts[0] and "$acceptance_criteria_block" not in llm.prompts[0]
    assert 'test("positive — valid login @smoke", async ({ action }) => {' in spec
    assert "annotation" not in spec
    plans = load_payload("test_plans", str(proj / "test_creation" / "test_plans.json"))
    assert all("tc_id" not in t for t in plans["M01_BS_001"]["tests"])
    assert "dropped_tests" not in plans["M01_BS_001"]
    assert not (proj / "test_creation" / "traceability.json").exists()


def test_unexpressible_plan_is_kept_so_the_reason_is_missing_locator(tmp_path, monkeypatch):
    empty = {"tests": [], "missing_actions": [], "missing_locators": ["quantity_input"]}
    monkeypatch.setattr(PlanLLM, "generate", lambda self, prompt: json.dumps(empty))
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent

    proj = _scriptgen_project(tmp_path, monkeypatch, True)
    agent = ScriptGenerationAgent(settings={})
    agent._registry.get_llm = MagicMock(return_value=PlanLLM())
    with patch.object(ScriptGenerationAgent, "_validate_locator_map_live", return_value=set()), \
         patch("agents.test_creation.script_generation.agent.write_named_locator_map",
               return_value={"added": [], "updated": [], "possibly_removed": []}), \
         patch("agents.test_creation.script_generation.agent.update_catalog"), \
         patch("agents.test_creation.script_generation.agent.flag_missing_capability"):
        out = agent.execute({"project_name": "shop", "requirements": {"enabled": True},
                             "modules": [{"id": "M01", "url": "https://shop.test/login"}]}, {})
    assert out["scripts_generated"] == 0
    plans = load_payload("test_plans", str(proj / "test_creation" / "test_plans.json"))
    assert plans["M01_BS_001"]["missing_locators"] == ["quantity_input"]
    # no spec at all for the module → module_not_generated wins; with a spec elsewhere it would be missing_locator
    trace = load_payload("traceability", str(proj / "test_creation" / "traceability.json"))
    assert trace["acs"]["AC-01.1"]["uncovered_reason"]["code"] == "module_not_generated"


def test_orchestrator_hints_when_cached_discovery_skips_requirements(tmp_path, monkeypatch, caplog):
    from agents.orchestrator.agent import OrchestratorAgent

    monkeypatch.setattr("agents.orchestrator.agent._PROJECTS_DIR", str(tmp_path))
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.logger = MagicMock()
    orch._hint_missing_requirements("shop", {"requirements": {"enabled": True}})
    assert "python -m tools.requirements.build --project shop" in orch.logger.warning.call_args[0][0]
    orch.logger.reset_mock()
    orch._hint_missing_requirements("shop", {"requirements": {"enabled": False}})
    orch.logger.warning.assert_not_called()
