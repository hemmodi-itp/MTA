"""Phase 1 — requirements.json per-module upsert, project-level service + build CLI, Agent-Eval enrichment (D3),
ac_ids surviving the business-scenario model, and TestData recording what its caps removed."""

import json

import pytest

from contracts.artifacts import load_payload, save_artifact
from tools.requirements import store
from tools.requirements.extract import ExtractionResult
from tools.requirements.models import Requirement

BRD_M01 = "### REQ-01 Login\n- AC-01.1: Valid credentials land on the Products page.\n"
BRD_M02 = "### REQ-02 Catalogue\n- AC-02.1: The product list is paginated with 5 products per page.\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    p = tmp_path / "shop"
    (p / "inputs").mkdir(parents=True)
    (p / "inputs" / "brd_M01.md").write_text(BRD_M01, encoding="utf-8")
    (p / "inputs" / "brd_M02.md").write_text(BRD_M02, encoding="utf-8")
    (p / "project.yaml").write_text(
        "project:\n  name: shop\nrequirements:\n  enabled: true\nmodules:\n"
        "  - {id: M01, url: 'https://s.test/1', brd_file: brd_M01.md}\n"
        "  - {id: M02, url: 'https://s.test/2', brd_file: brd_M02.md}\n", encoding="utf-8")
    return p


def _req(rid, module, ac_id):
    return Requirement.model_validate({"id": rid, "title": rid, "module_id": module, "acceptance_criteria": [
        {"id": ac_id, "statement": f"{ac_id} text", "testability": "ui", "testability_reason": "r",
         "priority": "P2"}]})


def test_upsert_replaces_only_the_module(project):
    store.upsert_module("shop", "M01", ExtractionResult(requirements=[_req("REQ-01", "M01", "AC-01.1")]), "a.md")
    store.upsert_module("shop", "M02", ExtractionResult(requirements=[_req("REQ-02", "M02", "AC-02.1")]), "b.md")
    store.upsert_module("shop", "M01", ExtractionResult(requirements=[_req("REQ-01", "M01", "AC-01.5")],
                                                        status="degraded", limitations=["no LLM"]), "a.md")
    doc = store.load_requirements("shop")
    assert [a.id for a in doc.criteria()] == ["AC-02.1", "AC-01.5"]
    assert doc.modules["M01"].status == "degraded" and doc.modules["M01"].limitations == ["no LLM"]
    assert doc.modules["M02"].brd_file == "b.md"
    raw = json.loads((project / "test_comprehension" / "requirements.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2 and raw["artifact"] == "requirements"
    assert store.reserved_ids(doc, "M01") == {"REQ-02": "REQ-02", "AC-02.1": "AC-02.1 text"}


def test_flat_project_uses_project_key(project):
    store.upsert_module("shop", None, ExtractionResult(requirements=[_req("REQ-01", None, "AC-01.1")]))
    assert list(store.load_requirements("shop").modules) == [store.FLAT_MODULE_KEY]


def test_build_cli_without_llm(project, capsys):
    from tools.requirements.build import build

    save_artifact("business_scenarios", str(project / "test_comprehension" / "business_scenarios.json"),
                  {"scenarios": [{"scenario_id": "M02_BS_001", "module_id": "M02", "title": "Paginate products",
                                  "steps": ["open the product list"], "expected_result": "5 products per page"}]})
    assert build("shop", no_llm=True) == 0
    out = capsys.readouterr().out
    assert "M01: 1 requirement(s), 1 criteria" in out and "status=degraded" in out
    scen = load_payload("business_scenarios", str(project / "test_comprehension" / "business_scenarios.json"))
    assert scen["scenarios"][0]["ac_ids"] == ["AC-02.1"]
    assert (project / "test_creation" / "traceability.json").exists()


def test_build_cli_single_module_and_unknown_module(project, capsys):
    from tools.requirements.build import build

    assert build("shop", module="M02", no_llm=True) == 0
    assert [r.id for r in store.load_requirements("shop").requirements] == ["REQ-02"]
    assert build("shop", module="M09", no_llm=True) == 2


def test_prompt_criteria_include_shared_ones_held_by_another_module():
    from tools.requirements.models import RequirementsDoc
    from tools.requirements.service import criteria_for_prompt

    ac = lambda i, s: {"id": i, "statement": s, "testability": "ui", "testability_reason": "r", "priority": "P2"}
    doc = RequirementsDoc.model_validate({
        "requirements": [
            {"id": "REQ-01", "title": "Login", "module_id": "M01", "acceptance_criteria": [
                ac("AC-01.6", "All API endpoints except /api/health require a session")]},
            {"id": "REQ-07", "title": "Admin", "module_id": "M06", "acceptance_criteria": [
                ac("AC-07.1", "Admin page for administrators only")]}],
        "warnings": [{"id": "AC-01.6", "module_id": "M06", "kind": "duplicate_of_other_module"},
                     {"id": "AC-01.6", "module_id": "M02", "kind": "split_rejected"}]})
    assert [c["id"] for c in criteria_for_prompt(doc, "M06")] == ["AC-07.1", "AC-01.6"]
    assert [c["id"] for c in criteria_for_prompt(doc, "M02")] == []
    assert [c["id"] for c in criteria_for_prompt(doc, "M01")] == ["AC-01.6"]


def test_relink_only_unlinked_leaves_existing_links(project):
    from tools.requirements.service import relink_project_scenarios

    store.upsert_module("shop", "M06", ExtractionResult(requirements=[Requirement.model_validate({
        "id": "REQ-07", "title": "Admin", "module_id": "M06", "acceptance_criteria": [
            {"id": "AC-07.1", "statement": "The Admin page is available only to administrators",
             "testability": "ui", "testability_reason": "r", "priority": "P1"}]})]))
    path = str(project / "test_comprehension" / "business_scenarios.json")
    save_artifact("business_scenarios", path, {"scenarios": [
        {"scenario_id": "M01_BS_005", "module_id": "M01", "title": "Admin page access",
         "steps": ["open the Admin page as an administrator"], "expected_result": "the page is available"},
        {"scenario_id": "M01_BS_001", "module_id": "M01", "title": "Admin page", "ac_ids": ["AC-99.1"],
         "ac_link_source": "llm"}]})
    assert relink_project_scenarios("shop", only_unlinked=True) == 2
    by_id = {s["scenario_id"]: s for s in load_payload("business_scenarios", path)["scenarios"]}
    assert by_id["M01_BS_005"]["ac_ids"] == ["AC-07.1"] and by_id["M01_BS_005"]["ac_link_source"] == "similarity"
    assert by_id["M01_BS_001"]["ac_ids"] == ["AC-99.1"]          # existing links untouched


def test_document_source_detection():
    from types import SimpleNamespace

    from tools.requirements.service import document_source

    assert document_source([SimpleNamespace(file_name="synthetic_brd.md")]) == "dom_inferred"
    assert document_source([SimpleNamespace(file_name="brd.md")], {"requirements_source": "dom_inferred"}) == "dom_inferred"
    assert document_source([SimpleNamespace(file_name="brd.md")]) == "brd"


# ── Agent-Eval enrichment (D3) ───────────────────────────────────────────────

def test_agent_eval_rows_gain_additive_deterministic_fields():
    from agents.comprehension.brd_builder.agent import normalize_requirements
    from tools.requirements.brd_index import BrdIndex

    brd = ("Users must log in with a password before checkout. A name of exactly 50 characters is accepted and 51 "
           "or more is rejected.")
    reqs, dropped = normalize_requirements([{
        "title": "Login", "description": "Users must log in with a password before checkout.",
        "priority": "low", "source_quote": "Users must log in with a password before checkout",
        "acceptance_criteria": [{"statement": "A name of exactly 50 characters is accepted and 51 or more is rejected",
                                 "oracle_hint": "deterministic"}]}], BrdIndex(brd))
    (r,) = reqs
    assert dropped == 0 and r["code"] == "REQ-01" and r["priority"] == "low"           # existing fields unchanged
    assert set(r["risk_tags"]) == {"auth", "payment"} and r["priority_p"] == "P1"       # floor rule lifts "low"
    c = r["criteria"][0]
    assert c["code"] == "AC-01.1" and c["atomic"] is False and "positive_and_negative" in c["atomicity_issues"]


# ── business scenarios keep ac_ids end to end ────────────────────────────────

def test_export_scenarios_preserves_ac_ids_and_omits_empty(tmp_path):
    from tools.comprehension.export_scenarios import export_scenarios
    from tools.comprehension.models import BusinessScenario

    base = dict(title="t", business_objective="o", actor="a", preconditions=[], steps=["s"], expected_result="e")
    export_scenarios([BusinessScenario(scenario_id="M01_BS_001", ac_ids=["AC-01.1"], ac_link_source="llm", **base)],
                     str(tmp_path), "p", module_ids=["M01"])
    # a second module's export round-trips the first module's scenarios through the model: links must survive
    export_scenarios([BusinessScenario(scenario_id="M02_BS_001", **base)], str(tmp_path), "p", module_ids=["M02"])
    scen = {s["scenario_id"]: s for s in load_payload("business_scenarios",
                                                       str(tmp_path / "business_scenarios.json"))["scenarios"]}
    assert scen["M01_BS_001"]["ac_ids"] == ["AC-01.1"] and scen["M01_BS_001"]["ac_link_source"] == "llm"
    assert "ac_ids" not in scen["M02_BS_001"] and "ac_link_source" not in scen["M02_BS_001"]


def test_scenario_loaders_keep_ac_ids(tmp_path):
    from tools.test_creation.testdata.load_scenarios import load_scenarios

    (tmp_path / "business_scenarios.json").write_text(json.dumps({"scenarios": [
        {"scenario_id": "S", "title": "t", "business_objective": "o", "actor": "a", "preconditions": [],
         "steps": ["s"], "expected_result": "e", "ac_ids": ["AC-01.1"]}]}), encoding="utf-8")
    assert load_scenarios(str(tmp_path))[0].ac_ids == ["AC-01.1"]


# ── TestData records capped variants ─────────────────────────────────────────

def test_capped_variants_are_recorded_and_omitted_when_zero():
    from tools.comprehension.models import BusinessScenario
    from tools.test_creation.testdata.generate_test_data import _build_model

    sc = BusinessScenario(scenario_id="S", title="t", business_objective="o", actor="a", preconditions=[],
                          steps=["s"], expected_result="e")
    nv = lambda t: {"variant_type": t, "description": t, "iterations": [{"fields": [], "expected_error": "x"}]}
    capped = _build_model({"negative_variants": [nv("negative"), nv("negative"), nv("boundary"), nv("boundary"),
                                                 nv("boundary")]}, sc, 1)
    assert capped.capped_variants == {"negative": 1, "boundary": 2}
    assert capped.model_dump()["capped_variants"] == {"negative": 1, "boundary": 2}
    plain = _build_model({"negative_variants": [nv("negative")]}, sc, 1)
    assert "capped_variants" not in plain.model_dump()
