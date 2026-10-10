"""Phase 1.1 — AC extraction schema tests: requirements.json / traceability.json models, the LLM response
contract, contracts registration and the exported JSON Schemas."""

import json
import os

import pytest
from pydantic import ValidationError

from contracts.artifacts import load_payload, save_artifact
from contracts.artifacts.boundary import STEP_ARTIFACTS
from contracts.artifacts.paths import artifact_path, iter_project_artifacts
from contracts.artifacts.registry import ARTIFACTS
from tools.requirements.models import (
    AcceptanceCriterion,
    LlmRequirementsResponse,
    RequirementsDoc,
    TraceabilityDoc,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _ac(**over):
    base = dict(id="AC-01.1", statement="Valid login lands on Products", testability="ui",
                testability_reason="observable in the UI", priority="P1")
    base.update(over)
    return base


def _doc(acs=None, **over):
    return {"requirements": [{"id": "REQ-01", "title": "Auth", "module_id": "M01",
                              "acceptance_criteria": acs if acs is not None else [_ac()]}], **over}


# ── AcceptanceCriterion ──────────────────────────────────────────────────────

def test_valid_criterion_has_defaults():
    ac = AcceptanceCriterion.model_validate(_ac())
    assert ac.source == "brd" and ac.atomic is True and ac.risk_tags == [] and ac.is_leaf


@pytest.mark.parametrize("bad_id", ["AC-1", "REQ-01.1", "AC-01", "ac-01.1", "AC-01.1.2.3", "AC-01.x"])
def test_criterion_id_format_is_enforced(bad_id):
    with pytest.raises(ValidationError):
        AcceptanceCriterion.model_validate(_ac(id=bad_id))


@pytest.mark.parametrize("good_id", ["AC-01.1", "AC-003.12", "AC-03.2.1"])
def test_criterion_id_formats_accepted(good_id):
    AcceptanceCriterion.model_validate(_ac(id=good_id))


@pytest.mark.parametrize("field,value", [
    ("testability", "browser"), ("priority", "P4"), ("priority", "high"),
    ("risk_tags", ["security"]), ("quote_match", "partial"), ("source", "llm"),
    ("confidence", 1.5), ("support", -0.1),
])
def test_enum_and_range_violations_rejected(field, value):
    with pytest.raises(ValidationError):
        AcceptanceCriterion.model_validate(_ac(**{field: value}))


def test_testability_reason_is_mandatory():
    with pytest.raises(ValidationError):
        AcceptanceCriterion.model_validate(_ac(testability="not_testable", testability_reason=""))


def test_quote_verified_requires_a_match():
    with pytest.raises(ValidationError):
        AcceptanceCriterion.model_validate(_ac(quote_verified=True, quote_match="none"))
    AcceptanceCriterion.model_validate(_ac(quote_verified=True, quote_match="fuzzy"))


def test_child_ids_must_extend_parent():
    AcceptanceCriterion.model_validate(_ac(id="AC-03.2", children=["AC-03.2.1", "AC-03.2.2"], atomic=False))
    AcceptanceCriterion.model_validate(_ac(id="AC-03.2.1", parent_id="AC-03.2"))
    with pytest.raises(ValidationError):
        AcceptanceCriterion.model_validate(_ac(id="AC-03.2", children=["AC-04.1.1"]))
    with pytest.raises(ValidationError):
        AcceptanceCriterion.model_validate(_ac(id="AC-04.1.1", parent_id="AC-03.2"))


# ── RequirementsDoc ──────────────────────────────────────────────────────────

def test_requirement_id_format_is_enforced():
    with pytest.raises(ValidationError):
        RequirementsDoc.model_validate({"requirements": [{"id": "R-1", "title": "x"}]})


def test_duplicate_ids_rejected():
    with pytest.raises(ValidationError):
        RequirementsDoc.model_validate(_doc([_ac(), _ac()]))
    with pytest.raises(ValidationError):
        RequirementsDoc.model_validate({"requirements": [{"id": "REQ-01", "title": "a"},
                                                         {"id": "REQ-01", "title": "b"}]})


def test_leaf_and_module_helpers():
    doc = RequirementsDoc.model_validate(_doc([
        _ac(id="AC-01.1"),
        _ac(id="AC-01.2", children=["AC-01.2.1", "AC-01.2.2"], atomic=False),
        _ac(id="AC-01.2.1", parent_id="AC-01.2"),
        _ac(id="AC-01.2.2", parent_id="AC-01.2"),
    ]))
    assert [a.id for a in doc.leaf_criteria()] == ["AC-01.1", "AC-01.2.1", "AC-01.2.2"]
    assert doc.leaf_criteria("M02") == []
    assert doc.requirement_of()["AC-01.2.2"].id == "REQ-01"


def test_envelope_round_trip_through_contracts(tmp_path):
    doc = RequirementsDoc.model_validate(_doc(project="p"))
    path = str(tmp_path / "test_comprehension" / "requirements.json")
    os.makedirs(os.path.dirname(path))
    save_artifact("requirements", path, doc.model_dump(mode="json"))
    raw = json.load(open(path, encoding="utf-8"))
    assert raw["schema_version"] == 2 and raw["artifact"] == "requirements"
    again = RequirementsDoc.model_validate(load_payload("requirements", path))
    assert again == doc


def test_traceability_round_trip(tmp_path):
    trace = TraceabilityDoc.model_validate({
        "acs": {"AC-01.1": {"req_id": "REQ-01", "tc_ids": ["M01_TC_001"], "status": "covered"}},
        "tests": {"M01_TC_001": {"ac_ids": ["AC-01.1"], "latest_result": {"status": "passed"}}},
    })
    path = str(tmp_path / "test_creation" / "traceability.json")
    os.makedirs(os.path.dirname(path))
    save_artifact("traceability", path, trace.model_dump(mode="json"))
    assert TraceabilityDoc.model_validate(load_payload("traceability", path)) == trace


def test_traceability_rejects_unknown_status():
    with pytest.raises(ValidationError):
        TraceabilityDoc.model_validate({"tests": {"t": {"latest_result": {"status": "green"}}}})


# ── LLM response contract ────────────────────────────────────────────────────

def test_llm_response_requires_structure_not_enum_values():
    ok = LlmRequirementsResponse.model_validate({"requirements": [
        {"title": "Auth", "acceptance_criteria": [{"statement": "x", "testability": "weird", "priority": "P9"}]}]})
    assert ok.requirements[0].acceptance_criteria[0].testability == "weird"   # coerced later by classify
    for bad in ({}, {"requirements": "nope"}, {"requirements": [{"acceptance_criteria": []}]},
                {"requirements": [{"title": "t", "acceptance_criteria": [{"statement": ""}]}]}):
        with pytest.raises(ValidationError):
            LlmRequirementsResponse.model_validate(bad)


# ── contracts registration ───────────────────────────────────────────────────

def test_new_artifacts_are_registered_and_mapped(tmp_path):
    assert ARTIFACTS["requirements"].kind == "dict" and ARTIFACTS["traceability"].kind == "dict"
    assert "requirements" in STEP_ARTIFACTS["discovery"] and "requirements" in STEP_ARTIFACTS["comprehension"]
    for step in ("script_generation", "ui_execution", "healing", "reporting"):
        assert "traceability" in STEP_ARTIFACTS[step]
    pdir = str(tmp_path)
    assert artifact_path(pdir, "requirements").endswith(os.path.join("test_comprehension", "requirements.json"))
    assert artifact_path(pdir, "traceability").endswith(os.path.join("test_creation", "traceability.json"))
    legacy = tmp_path / "comprehension"
    legacy.mkdir()
    (legacy / "requirements.json").write_text("{}", encoding="utf-8")
    assert artifact_path(pdir, "requirements", existing_only=True).endswith(
        os.path.join("comprehension", "requirements.json"))
    assert ("requirements", str(legacy / "requirements.json")) in list(iter_project_artifacts(pdir))


def test_exported_schemas_exist_and_mirror_models():
    for name in ("requirements", "traceability"):
        path = os.path.join(ROOT, "schemas", f"{name}.v2.schema.json")
        schema = json.load(open(path, encoding="utf-8"))
        assert schema["properties"]["artifact"]["const"] == name
