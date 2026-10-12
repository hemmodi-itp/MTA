"""Phase 3 — design() end to end, acceptance criteria on buggy_shop, LLM hint sanitising, TestDesignAgent,
locator merge, and the ScriptGeneration / tracing / traceability integration."""

import copy
import json
import os
import re
import shutil
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tools.benchmark.design_metrics import ACCEPTANCE_CATEGORIES, bug_targeting, design_summary
from tools.test_design.cases import stable_json
from tools.test_design.design import design
from tools.test_design.inputs import DesignInputs
from tools.test_design.llm import interpret_module, sanitize
from tools.test_design.locators import merge_form_locators
from tools.test_design.models import DesignHints, TestCasesDoc

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "test_design", "buggy_shop")
BUGS = yaml.safe_load(open(os.path.join(ROOT, "benchmarks", "apps", "buggy_shop", "bugs.yaml"), encoding="utf-8"))["bugs"]
BUDGET = {"max_tests": 400, "max_runtime_minutes": 45}


@pytest.fixture(scope="module")
def base_inp():
    return DesignInputs.load(FIXTURE, "bench_buggy_shop")


@pytest.fixture
def inp(base_inp):
    return copy.deepcopy(base_inp)


# ── acceptance criteria (plan Phase 3) ────────────────────────────────────────

def test_generators_are_deterministic_byte_identical(base_inp):
    a = stable_json(design(copy.deepcopy(base_inp), "thorough", BUDGET))
    b = stable_json(design(copy.deepcopy(base_inp), "thorough", BUDGET))
    assert a == b
    reloaded = DesignInputs.load(FIXTURE, "bench_buggy_shop")         # fresh load, same files
    assert stable_json(design(reloaded, "thorough", BUDGET)) == a


def test_standard_profile_meets_phase3_acceptance(inp):
    doc = design(inp, "standard", BUDGET)
    TestCasesDoc.model_validate(doc)
    s = design_summary(doc, BUGS)
    assert s["ac_coverage_pct"] >= 90.0                                  # ≥ 90% of testable ACs
    acc = [t for t in s["targeting"] if t["category"] in ACCEPTANCE_CATEGORIES]
    assert len(acc) == 5 and all(t["targeted"] for t in acc), acc       # every validation + state-machine bug
    assert doc["budget"]["respected"] is True                            # budget respected
    assert doc["budget"]["selected"] <= BUDGET["max_tests"]
    assert doc["budget"]["est_runtime_minutes"] <= BUDGET["max_runtime_minutes"]


def test_validation_bugs_are_targeted_by_the_right_technique(inp):
    t = {x["id"]: x for x in bug_targeting(design(inp, "standard", BUDGET), BUGS)}
    assert "bva" in t["BUG_01"]["techniques"]                            # name of exactly 50 rejected
    assert {"bva", "ep"} & set(t["BUG_21"]["techniques"])                # quantity 0 / -1
    assert t["BUG_10"]["targeted"]                                       # checkout with empty cart


def test_smaller_budget_cuts_with_reason_and_keeps_floor(inp):
    doc = design(inp, "thorough", {"max_tests": 120, "max_runtime_minutes": 45})
    assert doc["summary"]["cut"] > 0 and all(c["reason"] == "budget" for c in doc["cut"])
    assert doc["summary"]["ac_coverage_pct"] == 100.0                    # the floor survives the cut
    assert len(doc["test_cases"]) == doc["summary"]["selected"]


def test_brd_vs_observed_conflict_is_recorded(inp):
    doc = design(inp, "standard", BUDGET)
    assert {"ac_id": "AC-05.1.1", "form_id": "F-f9540101fa", "field": "quantity", "probe": "empty"} == {
        k: doc["conflicts"][0][k] for k in ("ac_id", "form_id", "field", "probe")}
    qty_empty = [c for c in doc["test_cases"] if c["target"].get("field") == "quantity" and c["test_type"] == "negative"]
    assert qty_empty                                                     # the BRD oracle is kept, not dropped


def test_profiles_are_nested(base_inp):
    ids = {p: {c["id"] for c in design(copy.deepcopy(base_inp), p, {"max_tests": 5000, "max_runtime_minutes": 5000})
               ["test_cases"]} for p in ("smoke", "standard", "thorough", "exhaustive")}
    assert ids["smoke"] < ids["standard"] < ids["thorough"] < ids["exhaustive"]


# ── LLM hints: sanitised, additive only ───────────────────────────────────────

def _hints(**kw):
    base = {"decision_tables": [], "ac_links": [], "extra_cases": [], "negative_paths": []}
    base.update(kw)
    return DesignHints.model_validate(base)


def test_sanitize_drops_every_unchecked_reference(inp):
    h = _hints(
        decision_tables=[
            {"ac_id": "AC-05.3.2", "conditions": ["valid_code", "already_applied"], "actions": ["applied", "refused"],
             "rules": [{"when": {"valid_code": True, "already_applied": True}, "then": "refused"},
                       {"when": {"valid_code": True}, "then": "not an action"}]},
            {"ac_id": "AC-01.1", "conditions": ["a", "b"], "actions": ["x"], "rules": [{"when": {"a": True}, "then": "x"}]}],
        ac_links=[{"case_id": "TC-unlisted", "ac_ids": ["AC-05.3.1"]}, {"case_id": "TC-1", "ac_ids": ["AC-99.9", "AC-05.3.1"]}],
        extra_cases=[{"ac_ids": ["AC-05.3.2"], "title": "Apply SAVE10 twice keeps the total", "test_type": "negative",
                      "steps_outline": ["apply SAVE10", "apply SAVE10 again"], "expected": "Discount already applied"},
                     {"ac_ids": ["AC-01.1"], "title": "Other module case", "test_type": "positive",
                      "steps_outline": ["x"], "expected": "yes it works"}],
        negative_paths=[{"ac_id": "AC-05.3.1", "has_negative_path": True}, {"ac_id": "AC-01.1", "has_negative_path": False}])
    out = sanitize(h, inp, "M04", ["TC-1"])
    assert [d["ac_id"] for d in out["decision_tables"]] == ["AC-05.3.2"]          # other-module table dropped
    assert out["decision_tables"][0]["rules"] == [{"when": {"valid_code": True, "already_applied": True},
                                                   "then": "refused"}]           # rule with unknown action dropped
    assert out["ac_links"] == [{"case_id": "TC-1", "ac_ids": ["AC-05.3.1"]}]       # unknown AC / case dropped
    assert [e["title"] for e in out["extra_cases"]] == ["Apply SAVE10 twice keeps the total"]
    assert out["negative_paths"] == [{"ac_id": "AC-05.3.1", "has_negative_path": True}]


def test_hints_only_add_cases(base_inp):
    plain = design(copy.deepcopy(base_inp), "standard", BUDGET)
    from tools.test_design.design import extra_cases
    inp = copy.deepcopy(base_inp)
    hints = {"decision_tables": [{"ac_id": "AC-05.3.2", "conditions": ["valid_code", "already_applied"],
                                  "actions": ["10% off", "Discount already applied"],
                                  "rules": [{"when": {"valid_code": True, "already_applied": True}, "then": "Discount already applied"},
                                            {"when": {"valid_code": True, "already_applied": False}, "then": "10% off"}]}],
             "negative_paths": [], "ac_links": [], "extra_cases": []}
    extras = extra_cases([{"ac_ids": ["AC-05.2.2"], "title": "1 Gel Pen totals 1.01", "test_type": "positive",
                           "preconditions": [], "steps_outline": ["add 1 Gel Pen", "open the cart"],
                           "expected": "Total 1.01"}], inp, "M04")
    rich = design(inp, "standard", BUDGET, hints=hints, extras=extras)
    plain_ids, rich_ids = {c["id"] for c in plain["test_cases"]}, {c["id"] for c in rich["test_cases"]}
    assert plain_ids <= rich_ids                                          # nothing deterministic removed
    techniques = {c["technique"] for c in rich["test_cases"] if c["id"] not in plain_ids}
    assert techniques == {"decision_table", "llm_domain"}


class _JsonLLM:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def test_interpret_module_validates_and_repairs_once(inp):
    bad = json.dumps({"negative_paths": [{"ac_id": "AC-05.3.1"}]})           # missing has_negative_path
    good = json.dumps({"negative_paths": [{"ac_id": "AC-05.3.1", "has_negative_path": True}]})
    llm = _JsonLLM(bad, good)
    hints = interpret_module(llm, inp, "M04", [])
    assert hints.negative_paths[0].has_negative_path is True and len(llm.prompts) == 2
    assert "<untrusted_content" in llm.prompts[0] and "AC-05.3.1" in llm.prompts[0]


# ── locators ──────────────────────────────────────────────────────────────────

def test_merge_form_locators_reuses_same_module_and_adds_crawled_fields(inp):
    doc = design(inp, "standard", BUDGET)
    css_name = {"type": "css", "locator": '#product-form [name="name"]', "_module_id": "M03", "_source_locator_id": "L1"}
    role_name = {"type": "role", "locator": "textbox", "name": "Name", "_module_id": "M03"}
    existing = {"name": dict(role_name), "product_name": dict(css_name)}
    merged, added = merge_form_locators(existing, inp, doc["test_cases"])
    assert merged["name"] == role_name and merged["product_name"] == css_name     # never overwritten
    name_case = next(c for c in doc["test_cases"] if c["target"].get("form_id") == "F-69c120ba3f"
                     and c["target"].get("field") == "name")
    keys = name_case["locator_keys"]
    assert keys["name"] == "product_name"                                 # identical locator, same module → reused
    assert merged[keys["submit"]]["locator"] == '#product-form [type="submit"]'
    assert merged[keys["error"]] == dict(merged[keys["error"]], type="css", locator="div#form-errors.alert",
                                          _dynamic=True)                  # error area seen in the probes
    qty_case = next(c for c in doc["test_cases"] if c["target"].get("field") == "quantity")
    qkey = qty_case["locator_keys"]["quantity"]
    assert qkey in added and merged[qkey]["_source"] == "form_model"
    assert merged[qkey]["locator"] == '#add-to-cart-form [name="quantity"]' and "/products/" in merged[qkey]["_page_url"]
    search_case = next(c for c in doc["test_cases"] if c["target"].get("form_id") == "F-4dc9438dcb")
    assert merged[search_case["locator_keys"]["q"]]["locator"] == '#search-form [name="q"]'   # not role textbox
    again, added2 = merge_form_locators(merged, inp, doc["test_cases"])
    assert added2 == [] and again == merged                               # idempotent


def test_dom_rebuild_never_reports_form_model_entries_removed(tmp_path):
    from tools.test_creation.script_generator.build_dom_locator_map import build_named_locator_map
    existing = {"quantity": {"type": "role", "locator": "textbox", "name": "Quantity", "_module_id": "M04",
                             "_source": "form_model", "_page_url": "http://x/products/1"}}
    out = build_named_locator_map(str(tmp_path), existing, llm_reconcile=MagicMock(return_value={}))
    assert out["possibly_removed"] == [] and out["map"]["quantity"] == existing["quantity"]


# ── TestDesignAgent ───────────────────────────────────────────────────────────

def _project(tmp_path, monkeypatch, profile="standard", requirements=True):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    monkeypatch.setattr("agents.test_creation.test_design.agent._ASSETS_BASE", str(tmp_path))
    proj = tmp_path / "bench_buggy_shop"
    shutil.copytree(FIXTURE, proj)
    cfg = yaml.safe_load((proj / "project.yaml").read_text(encoding="utf-8"))
    cfg["requirements"] = {"enabled": requirements}
    cfg["test_generation"] = {"profile": profile, "max_negative_cases": 1} if profile else {"max_negative_cases": 1}
    (proj / "project.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return proj


class _StubLLM:
    """Plain object (a MagicMock would expose a fake `generate_json` that generate_json() prefers)."""

    def __init__(self, answer):
        self.answer, self.calls, self.error = answer, 0, None

    def generate(self, prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer


def _agent(answer=None):
    from agents.test_creation.test_design.agent import TestDesignAgent
    agent = TestDesignAgent(settings={})
    llm = _StubLLM(answer or json.dumps({"negative_paths": [], "decision_tables": [], "ac_links": [],
                                         "extra_cases": []}))
    agent._llm = MagicMock(return_value=llm)
    return agent, llm


def test_agent_writes_test_cases_and_locators(tmp_path, monkeypatch):
    proj = _project(tmp_path, monkeypatch)
    agent, llm = _agent()
    out = agent.execute({"project_name": "bench_buggy_shop"}, {})
    assert out["status"] == "success" and out["profile"] == "standard" and out["llm"] == "ok"
    doc = json.loads((proj / "test_creation" / "test_cases.json").read_text(encoding="utf-8"))
    TestCasesDoc.model_validate(doc)
    assert doc["generated_at"] and doc["summary"]["ac_coverage_pct"] == 100.0
    lm = json.loads((proj / "test_creation" / "locator_map.json").read_text(encoding="utf-8"))
    assert any(e.get("_source") == "form_model" for e in lm.values())
    assert llm.calls == 6                                                 # one call per module with testable ACs


def test_module_scoped_runs_call_only_their_module_and_reuse_the_cache(tmp_path, monkeypatch):
    proj = _project(tmp_path, monkeypatch)
    agent, llm = _agent()
    agent.execute({"project_name": "bench_buggy_shop", "modules": [{"id": "M04"}]}, {})
    doc = json.loads((proj / "test_creation" / "test_cases.json").read_text(encoding="utf-8"))
    assert llm.calls == 1 and doc["llm"]["modules"]["M04"] == "ok" and doc["llm"]["modules"]["M01"] == "skipped"
    agent.execute({"project_name": "bench_buggy_shop"}, {})              # whole project: M04 comes from the cache
    doc = json.loads((proj / "test_creation" / "test_cases.json").read_text(encoding="utf-8"))
    assert llm.calls == 6 and doc["llm"]["modules"]["M04"] == "cached" and doc["llm"]["status"] == "ok"
    agent.execute({"project_name": "bench_buggy_shop"}, {})              # unchanged criteria: no new calls
    assert llm.calls == 6


def test_agent_degrades_to_deterministic_when_the_llm_fails(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    agent, llm = _agent()
    llm.error = RuntimeError("quota")
    with patch("tools.test_design.llm.TRANSIENT_RETRY_DELAY_S", 0):
        out = agent.execute({"project_name": "bench_buggy_shop"}, {})
    assert out["status"] == "partial" and out["llm"] == "degraded"
    assert out["summary"]["ac_coverage_pct"] == 100.0


def test_agent_skips_without_profile_or_requirements(tmp_path, monkeypatch):
    proj = _project(tmp_path, monkeypatch, profile=None)
    agent, llm = _agent()
    assert agent.execute({"project_name": "bench_buggy_shop"}, {})["skipped"] is True
    assert not (proj / "test_creation" / "test_cases.json").exists() and llm.calls == 0
    shutil.rmtree(proj)
    _project(tmp_path, monkeypatch, requirements=False)
    assert agent.execute({"project_name": "bench_buggy_shop"}, {})["reason"] == "requirements_disabled"


def test_agent_llm_extras_go_through_semantic_dedup(tmp_path, monkeypatch):
    _project(tmp_path, monkeypatch)
    answer = json.dumps({"negative_paths": [], "decision_tables": [], "ac_links": [], "extra_cases": [
        {"ac_ids": ["AC-05.2.2"], "title": "One Gel Pen totals 1.01", "test_type": "positive",
         "steps_outline": ["add 1 Gel Pen to the cart", "open the cart"], "expected": "Total 1.01"}]})
    agent, _ = _agent(answer)
    calls = []

    def fake_dedup(self, request, state):
        calls.append(request)
        return {"approved": [], "rejected": request["proposed_test_cases"]}     # reject them all
    with patch("agents.test_creation.dedup.agent.SemanticDedupAgent.execute", fake_dedup):
        out = agent.execute({"project_name": "bench_buggy_shop"}, {})
    assert calls and calls[0]["existing_test_cases"]                         # deterministic cases = existing side
    doc = json.loads(open(out["output"]["test_cases"], encoding="utf-8").read())
    assert doc["llm"]["added"] == 0 and doc["llm"]["rejected_duplicates"] == 1   # kept only for M04 (its AC)
    assert not any(c["technique"] == "llm_domain" for c in doc["test_cases"])


# ── ScriptGeneration / tracing / traceability integration ─────────────────────

def test_reconcile_design_plan_keeps_one_test_per_case_and_records_the_rest():
    from agents.test_creation.script_generation.agent import _reconcile_design_plan
    chunk = [{"id": "TC-a", "title": "A", "test_type": "negative"}, {"id": "TC-b", "title": "B", "test_type": "boundary"},
             {"id": "TC-c", "title": "C", "test_type": "positive"}]
    ok = [{"action": "navigate"}, {"action": "verifyContainsText", "locator_key": "e", "value": "Name is required",
                                   "message": "m"}]
    plan = {"tests": [{"name": "A", "case_id": "TC-a", "type": "positive", "steps": ok},
                      {"name": "A again", "case_id": "TC-a", "steps": ok},
                      {"name": "invented", "steps": ok}],
            "dropped_tests": [{"test": "B", "reason": "placeholder_negative_dropped"}]}
    out = _reconcile_design_plan(plan, chunk)
    assert [(t["case_id"], t["type"]) for t in out["tests"]] == [("TC-a", "negative")]
    reasons = {(d.get("case_id"), d["reason"]) for d in out["dropped_tests"]}
    assert reasons == {(None, "not_in_design"), ("TC-a", "duplicate_case_test"),
                       ("TC-b", "placeholder_negative_dropped"), ("TC-c", "not_expressed")}


def test_design_locators_are_offered_only_when_live():
    from agents.test_creation.script_generation.agent import _with_design_locators
    lm = {"qty": {"description": "Quantity"}, "dead": {}, "name": {}}
    out = _with_design_locators([{"key": "name", "description": ""}],
                                [{"locator_keys": {"quantity": "qty", "x": "dead", "y": "missing", "name": "name"}}],
                                lm, {"dead"})
    assert [e["key"] for e in out] == ["name", "qty"]


def test_design_prompt_reuses_the_legacy_prompt_around_the_case_block():
    from agents.test_creation.script_generation.prompt import ACTION_LIBRARY_PROMPT, DESIGN_CASES_PROMPT
    legacy, design_t = ACTION_LIBRARY_PROMPT.template, DESIGN_CASES_PROMPT.template
    assert "== Test counts ==" in legacy and "== Test counts ==" not in design_t
    assert design_t.startswith(legacy.split("== Test counts ==")[0])
    assert design_t.endswith(legacy.split("== Verification contract", 1)[1])
    assert "$design_cases_json" in design_t and "EXACTLY ONE test per case" in design_t


def _scriptgen_design_project(tmp_path, monkeypatch):
    from contracts.artifacts import save_artifact
    from tools.requirements.models import RequirementsDoc
    monkeypatch.setattr("agents.test_creation.script_generation.agent._ASSETS_BASE", str(tmp_path))
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    proj = tmp_path / "shop"
    (proj / "test_comprehension").mkdir(parents=True)
    (proj / "test_creation" / "test_data").mkdir(parents=True)
    (proj / "project.yaml").write_text(yaml.safe_dump({
        "project": {"name": "shop"}, "requirements": {"enabled": True}, "test_generation": {"profile": "standard"},
        "modules": [{"id": "M01", "url": "https://shop.test/products/new"}]}), encoding="utf-8")
    scen = [{"scenario_id": "M01_BS_001", "title": "Create product", "module_id": "M01", "steps": ["create"],
             "ac_ids": ["AC-01.1"]},
            {"scenario_id": "M01_BS_002", "title": "Other", "module_id": "M01", "steps": ["x"], "ac_ids": ["AC-01.1"]}]
    save_artifact("business_scenarios", str(proj / "test_comprehension" / "business_scenarios.json"),
                  {"project": "shop", "scenarios": scen})
    doc = RequirementsDoc.model_validate({"project": "shop", "requirements": [
        {"id": "REQ-01", "title": "Products", "module_id": "M01", "acceptance_criteria": [
            {"id": "AC-01.1", "statement": "Name must be 1-50 characters", "testability": "ui",
             "testability_reason": "r", "priority": "P1", "risk_tags": []},
            {"id": "AC-01.2", "statement": "Name is required", "testability": "ui",
             "testability_reason": "r", "priority": "P2", "risk_tags": []}]}]})
    save_artifact("requirements", str(proj / "test_comprehension" / "requirements.json"), doc.model_dump(mode="json"))
    (proj / "test_creation" / "locator_map.json").write_text(json.dumps({
        "name": {"type": "role", "locator": "textbox", "name": "Name", "_module_id": "M01", "_source_locator_id": "LOC-1"},
        "save": {"type": "role", "locator": "button", "name": "Save", "_module_id": "M01", "_source": "form_model",
                 "_page_url": "https://shop.test/products/new"}}), encoding="utf-8")
    (proj / "test_creation" / "scenario_element_map.json").write_text(json.dumps(
        {"M01_BS_001": {"relevant_elements": [{"locator_id": "LOC-1"}]}}), encoding="utf-8")
    save_artifact("test_data", str(proj / "test_creation" / "test_data" / "test_data.json"), [])
    case = {"key": "k", "ac_link": "generator", "module_id": "M01", "level": "standard", "risk_score": 0.8,
            "roles": [], "preconditions": [], "cleanup": [], "source": "brd", "confidence": 1.0, "est_seconds": 9,
            "tags": [], "oracles": [], "steps_outline": ["submit"], "target": {"kind": "form", "field": "name"}}
    cases = [dict(case, id="TC-00000001", key="k1", title="Name max+1 (51 chars) is rejected", technique="bva",
                  test_type="negative", priority="P0", ac_ids=["AC-01.1"], scenario_id="M01_BS_001",
                  inputs={"name": {"value": "x" * 51}}, locator_keys={"name": "name", "submit": "save"}),
             dict(case, id="TC-00000002", key="k2", title="Name empty is rejected", technique="ep",
                  test_type="negative", priority="P2", ac_ids=["AC-01.2"], scenario_id="M01_BS_001",
                  inputs={"name": {"value": ""}}, locator_keys={"name": "name", "submit": "save"})]
    tc_doc = {"schema_version": 2, "artifact": "test_cases", "project": "shop", "profile": "standard",
              "content_hash": "x", "generated_at": None, "inputs": {}, "limitations": [],
              "budget": {"max_tests": 400, "max_runtime_minutes": 45.0, "selected": 2, "est_runtime_minutes": 0.3,
                         "respected": True, "p0_over_budget": False},
              "summary": {"generated": 3, "selected": 2, "cut": 1},
              "llm": {"status": "skipped"}, "page_hashes": {}, "test_cases": cases,
              "cut": [{"id": "TC-00000003", "title": "Cut one", "technique": "bva", "priority": "P3", "risk_score": 0.1,
                       "ac_ids": ["AC-01.9"], "reason": "budget"}], "conflicts": []}
    TestCasesDoc.model_validate(tc_doc)
    (proj / "test_creation" / "test_cases.json").write_text(json.dumps(tc_doc), encoding="utf-8")
    return proj


class _CaseLLM:
    """Implements only the FIRST case of each chunk, so the second must be reported not_expressed."""

    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        ids = re.findall(r'"id": "(TC-[0-9a-f]{8})"', prompt)
        return json.dumps({"tests": [{"name": "Name max+1 (51 chars) is rejected", "case_id": ids[0], "type": "positive",
                                      "steps": [{"action": "navigate"},
                                                {"action": "enterText", "locator_key": "name", "value": "x" * 51},
                                                {"action": "click", "locator_key": "save"},
                                                {"action": "verifyVisible", "locator_key": "name",
                                                 "message": "still on the form"}]}],
                           "missing_actions": [], "missing_locators": []})


def test_scriptgen_implements_design_cases_and_traces_them(tmp_path, monkeypatch):
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent
    proj = _scriptgen_design_project(tmp_path, monkeypatch)
    agent = ScriptGenerationAgent(settings={})
    llm = _CaseLLM()
    agent._registry.get_llm = MagicMock(return_value=llm)
    with patch.object(ScriptGenerationAgent, "_validate_locator_map_live", return_value=set()), \
         patch("agents.test_creation.script_generation.agent.write_named_locator_map",
               return_value={"added": [], "updated": [], "possibly_removed": []}), \
         patch("agents.test_creation.script_generation.agent.update_catalog"):
        out = agent.execute({"project_name": "shop", "requirements": {"enabled": True},
                             "test_design": {"enabled": True},
                             "modules": [{"id": "M01", "url": "https://shop.test/products/new"}]}, {})
    assert out["scripts_generated"] == 1                          # M01_BS_002 has no cases → no spec
    assert len(llm.prompts) == 1 and "EXACTLY ONE test per case" in llm.prompts[0]
    assert '"key": "save"' in llm.prompts[0]                      # form_model locator offered
    spec = next((proj / "test_creation" / "test_scripts" / "M01").glob("*.spec.ts")).read_text(encoding="utf-8")
    assert '"@P0", "@negative", "@regression", "@REQ-01", "@AC-01.1", "@bva"' in spec
    assert '{ type: "case", description: "TC-00000001" }' in spec
    plans = json.loads((proj / "test_creation" / "test_plans.json").read_text(encoding="utf-8"))
    plan = plans.get("plans", plans)["M01_BS_001"]
    assert plan["tests"][0]["type"] == "negative" and plan["tests"][0]["priority"] == "P0"
    assert {"test": "Name empty is rejected", "case_id": "TC-00000002", "reason": "not_expressed"} in plan["dropped_tests"]
    trace = json.loads((proj / "test_creation" / "traceability.json").read_text(encoding="utf-8"))
    assert trace["acs"]["AC-01.2"]["uncovered_reason"]["code"] == "not_expressed"


def test_design_reasons_budget_and_not_expressed():
    from tools.requirements.traceability import design_reasons
    doc = {"test_cases": [{"id": "TC-1", "title": "t", "ac_ids": ["AC-1"]}],
           "cut": [{"id": "TC-2", "ac_ids": ["AC-2", "AC-1"], "reason": "budget", "detail": "max_tests=1"}]}
    plans = {"S": {"dropped_tests": [{"case_id": "TC-1", "reason": "not_expressed"}]}}
    r = design_reasons(doc, plans)
    assert r["AC-1"].code == "not_expressed" and r["AC-2"].code == "budget"
    assert design_reasons(None, plans) == {}


# ── config / manifest / wiring / contracts ────────────────────────────────────

def test_manifest_passes_the_design_block(tmp_path, monkeypatch):
    from tools.project_manifest import load_project_manifest
    monkeypatch.setattr("tools.project_manifest._PROJECTS_DIR", str(tmp_path))
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "project.yaml").write_text(yaml.safe_dump({
        "test_generation": {"profile": "thorough", "budget": {"max_tests": 80}, "max_boundary_cases": 1}}), encoding="utf-8")
    td = load_project_manifest("p")["test_design"]
    assert td == {"enabled": True, "profile": "thorough", "budget": {"max_tests": 80, "max_runtime_minutes": 45.0},
                  "llm": True, "deprecated_caps": ["max_boundary_cases"]}


def test_workflow_and_registry_wiring():
    from agents.registry_setup import LEGACY_AGENTS
    from workflows.workflow_loader import load_workflow
    assert load_workflow("full_workflow").steps[1:4] == ["testdata", "test_design", "semantic_map"]
    assert load_workflow("test_test_creation_only").steps[:2] == ["testdata", "test_design"]
    assert ("test_design", "agents.test_creation.test_design.agent", "TestDesignAgent", {}) in LEGACY_AGENTS


def test_test_cases_contract_is_registered():
    from contracts.artifacts.boundary import STEP_ARTIFACTS
    from contracts.artifacts.paths import artifact_path
    from contracts.artifacts.registry import ARTIFACTS
    assert ARTIFACTS["test_cases"].model is TestCasesDoc
    assert "test_cases" in STEP_ARTIFACTS["test_design"]
    assert artifact_path("P", "test_cases").replace("\\", "/") == "P/test_creation/test_cases.json"


# -- regressions for the Phase 3 review findings ------------------------------

def test_permission_cell_keeps_brd_oracle_when_crawl_saw_a_bug(inp):
    for cell in inp.permission["states"]:
        if cell["url_template"] == "/admin":
            cell["access"]["user"] = "reachable"                       # crawl ran against a BUG_16 build
    doc = design(inp, "standard", BUDGET)
    case = next(c for c in doc["test_cases"] if c["title"].startswith("user opening /admin"))
    assert case["test_type"] == "negative"
    assert case["oracles"][0]["type"] == "access_blocked" and case["oracles"][0]["source"] == "brd"
    assert "brd-vs-observed" in case["tags"] and case["ac_ids"] == ["AC-07.1.2"]
    assert any(c["form_id"] == "page:/admin" and c["field"] == "user" for c in doc["conflicts"])


def test_guest_redirect_cells_are_not_linked_to_the_logout_rule(inp):
    from tools.test_design import role_matrix
    cell = next(c for c in role_matrix.generate(inp) if c["title"] == "guest opening /cart by direct URL is blocked")
    assert cell["ac_ids"] == ["AC-01.5"]                               # not AC-01.3 (logout invalidates session)


def _design_case(**kw):
    base = {"id": "TC-1", "title": "Name max+1 is rejected", "test_type": "negative",
            "target": {"kind": "form", "field": "name"}, "inputs": {"name": {"value": "x" * 51}}}
    base.update(kw)
    return base


def _test(steps, type_="positive"):
    return {"name": "t", "case_id": "TC-1", "type": type_, "steps": steps}


def test_retyped_placeholder_negative_is_dropped_after_reconcile():
    from agents.test_creation.script_generation.agent import _reconcile_design_plan
    steps = [{"action": "navigate"}, {"action": "enterText", "locator_key": "name", "value": "x" * 51},
             {"action": "verifyText", "locator_key": "h", "value": "", "message": "m"}]
    out = _reconcile_design_plan({"tests": [_test(steps)]}, [_design_case()])   # the LLM said "positive"
    assert out["tests"] == [] and out["dropped_tests"][0]["reason"] == "placeholder_negative_dropped"


def test_design_test_must_assert_and_must_use_the_value_under_test():
    from agents.test_creation.script_generation.agent import _reconcile_design_plan
    verify = {"action": "verifyContainsText", "locator_key": "e", "value": "Name must be at most 50", "message": "m"}
    no_assert = _reconcile_design_plan({"tests": [_test([{"action": "navigate"}])]}, [_design_case()])
    assert no_assert["dropped_tests"][0]["reason"] == "no_assertion"
    wrong_value = _reconcile_design_plan(
        {"tests": [_test([{"action": "enterText", "locator_key": "name", "value": "x" * 50}, verify])]}, [_design_case()])
    assert wrong_value["dropped_tests"][0]["reason"] == "input_not_used"
    good = _reconcile_design_plan(
        {"tests": [_test([{"action": "enterText", "locator_key": "name", "value": "x" * 51}, verify])]}, [_design_case()])
    assert len(good["tests"]) == 1 and good["dropped_tests"] == []
    upload = _design_case(target={"kind": "form", "field": "file"},
                          inputs={"file": {"value": {"file_name": "a.exe", "size_bytes": 10}}})
    assert _reconcile_design_plan({"tests": [_test([verify])]}, [upload])["dropped_tests"][0]["reason"] == "input_not_used"


def test_bva_keeps_a_real_minimum_when_only_the_maximum_is_defaulted():
    from tools.test_design import bva
    form = {"form_id": "F-pw", "url_template": "/register", "url": "http://x/register", "dom_id": "reg",
            "method": "post", "action": "/register", "submit": {"text": "Register"}, "probes": [],
            "fields": [{"name": "password", "label": "Password", "type": "password",
                        "locator": {"type": "role", "locator": "textbox", "name": "Password"},
                        "constraints": {"type": "password", "minlength": "8", "required": True}}]}
    inp = DesignInputs.from_artifacts("p", {}, {"requirements": []}, {"scenarios": []}, {"forms": [form]})
    pts = {c["key"].split("|")[-1]: c["inputs"]["password"]["length"] for c in bva.generate(inp)}
    assert pts == {"min-1": 7, "min": 8, "min+1": 9, "max": 255, "max+1": 256}


def test_whitespace_class_borrows_no_native_evidence(inp):
    from tools.test_design import ep
    cases = ep.generate(inp)
    case = next(c for c in cases if c["title"] == "Username: whitespace only is rejected")
    assert [o["type"] for o in case["oracles"]] == ["submission_rejected"]   # no native message / no_request
    empty = next(c for c in cases if c["title"] == "Username: empty is rejected")
    assert {"field_invalid", "no_request"} <= {o["type"] for o in empty["oracles"]}


def test_polarity_non_empty_cart_and_anonymous_access():
    from tools.test_design.use_case import is_negative
    assert not is_negative("Placing an order from a non-empty cart opens the order confirmation page")
    assert not is_negative("The Help page (`/help`) is available without signing in.")
    assert is_negative("Checkout with an empty cart does not create an order.")


def test_locator_merge_keeps_scope_and_never_reuses_an_unscoped_key(inp):
    form = next(f for f in inp.forms if f.form_id == "F-69c120ba3f")
    form.dom_id = ""                                   # no form id → the crawl's own (scoped) locator is used
    name = next(f for f in form.fields if f.name == "name")
    name.locator = dict(name.locator, scope={"type": "role", "locator": "dialog", "name": "New"})
    existing = {"name": {"type": "role", "locator": "textbox", "name": "Name", "_module_id": "M03"}}
    case = {"id": "TC-1", "module_id": "M03", "target": {"kind": "form", "form_id": "F-69c120ba3f", "field": "name"}}
    merged, _added = merge_form_locators(existing, inp, [case])
    key = case["locator_keys"]["name"]
    assert key != "name" and merged[key]["scope"]["locator"] == "dialog"


def test_dynamic_error_area_is_not_live_validated():
    from agents.test_creation.script_generation.agent import ScriptGenerationAgent
    agent = ScriptGenerationAgent(settings={})
    seen = []
    agent._get_validation_page = lambda module_id, url, setup: (seen.append(url), (None, None))[1]
    lm = {"err": {"type": "css", "locator": "div#e", "_module_id": "M1", "_dynamic": True, "_page_url": "http://x/a"},
          "f": {"type": "css", "locator": "#f [name=a]", "_module_id": "M1", "_page_url": "http://x/b"}}
    assert agent._validate_locator_map_live("p", "p", lm, "", {}, {}) == set()
    assert seen == ["http://x/b"]


def test_doc_accounting_and_honest_metrics(base_inp):
    doc = design(copy.deepcopy(base_inp), "standard", BUDGET)
    s = doc["summary"]
    assert s["generated"] == s["selected"] + s["cut"] + s["excluded_by_profile"]
    m = design_summary(doc, BUGS, implemented=set())
    assert m["ac_coverage_pct_by_technique"] < m["ac_coverage_pct"]   # use_case restates every AC
    assert m["acceptance_bugs_targeted_by_technique"] >= 2             # BVA / EP really aim at BUG_01 / BUG_21
    assert m["acceptance_bugs_targeted_implemented"] == 0 and m["cases_implemented"] == 0


def test_legacy_traceability_ignores_a_leftover_test_cases_file(tmp_path, monkeypatch):
    from tools.requirements import traceability
    _scriptgen_design_project(tmp_path, monkeypatch)
    build = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(traceability, "build", build)
    monkeypatch.setattr(traceability, "save_traceability", MagicMock())
    traceability.refresh_project("shop", {"requirements": {"enabled": True}, "test_design": {"enabled": False}})
    assert build.call_args.kwargs["design_doc"] is None
    traceability.refresh_project("shop", {"requirements": {"enabled": True}, "test_design": {"enabled": True}})
    assert build.call_args.kwargs["design_doc"]["artifact"] == "test_cases"


def test_determinism_across_processes_and_hash_seeds():
    import subprocess
    import sys
    code = ("import hashlib; from tools.test_design.inputs import DesignInputs; from tools.test_design.design import design; "
            "from tools.test_design.cases import stable_json; "
            f"d = design(DesignInputs.load({FIXTURE!r}, 'b'), 'thorough', {{'max_tests': 400, 'max_runtime_minutes': 45}}); "
            "print(hashlib.sha1(stable_json(d).encode()).hexdigest())")
    outs = set()
    for seed in ("0", "1", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        outs.add(res.stdout.strip())
    assert len(outs) == 1
