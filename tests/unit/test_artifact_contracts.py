"""Phase 0.7 — artifact contracts: round trips, v1 -> v2 migration, real-project
fixtures, schema export freshness, and orchestrator boundary enforcement."""

import copy
import json
import os
import shutil

import pytest

from contracts.artifacts import (
    ARTIFACTS,
    SCHEMA_VERSION,
    ArtifactVersionError,
    detect_version,
    load_payload,
    load_records,
    save_artifact,
    to_v1,
    to_v2,
    validate_document,
    validate_file,
    wrap,
)
from contracts.artifacts.boundary import STEP_ARTIFACTS, apply_enforcement, validate_step_outputs
from contracts.artifacts.paths import artifact_path, iter_project_artifacts

pytestmark = pytest.mark.mta  # pure contracts code; no legacy agent stack needed

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

V1 = {
    "dom_elements": {"url": "https://a.test", "project": "p", "elements": [
        {"locator_id": "LOC-0001", "tag": "button", "display_text": "Go",
         "recommended_locator": {"type": "id", "value": "#go", "score": 140}}]},
    "business_scenarios": {"project": "p", "total_scenarios": 1, "scenarios": [
        {"scenario_id": "BS-001", "title": "Login", "steps": ["open", "submit"], "module_id": "M01"}]},
    "test_data": [{"testdata_id": "TD-001", "scenario_id": "BS-001", "scenario_title": "Login", "actor": "user",
                   "positive_dataset": [{"field_name": "fill_user", "field_type": "text", "value": "alice"}],
                   "negative_variants": [{"variant_id": "NEG-001", "variant_type": "negative", "description": "empty",
                                          "iterations": [{"fields": [{"field_name": "fill_user", "value": ""}],
                                                          "expected_error": "Required"}]}]}],
    "scenario_element_map": {"BS-001": {"scenario_title": "Login", "relevant_elements": [
        {"locator_id": "LOC-0001", "playwright_expr": "page.locator('#go')", "cluster": "login", "confidence": 0.9}]}},
    "test_plans": {"BS-001": {"tests": [{"name": "positive", "type": "positive", "steps": [
        {"action": "navigate"}, {"action": "click", "locator_key": "go"}]}],
        "missing_actions": [], "missing_locators": []}},
    "test_suite": {"project": "p", "specs": [{"spec_id": "BS-001", "file": "M01/test.spec.ts", "status": "new"}],
                   "updated_at": "2026-10-10", "total_scenarios": 1, "new_additions": []},
    "execution_results": {"project": "p", "passed": 1, "failed": 0, "skipped": 0,
                          "results": [{"spec_file": "M01/test.spec.ts", "test_title": "t", "status": "success"}]},
}


@pytest.mark.parametrize("name", sorted(V1))
def test_v1_to_v2_round_trip(name, tmp_path):
    v1 = copy.deepcopy(V1[name])
    assert detect_version(name, v1) == 1
    v2 = to_v2(name, v1)
    assert v2["schema_version"] == SCHEMA_VERSION and v2["artifact"] == name
    assert v1 == V1[name], "migration must not mutate its input"
    assert validate_document(name, v2).ok
    assert to_v2(name, v2) == v2, "v2 -> v2 is the identity"
    assert to_v1(name, v2) == V1[name], "downgrade restores the v1 body exactly"

    path = str(tmp_path / f"{name}.json")
    save_artifact(name, path, copy.deepcopy(v1))
    on_disk = json.loads(open(path, encoding="utf-8").read())
    assert on_disk["schema_version"] == 2
    # load_payload returns the shape existing callers use
    payload = load_payload(name, path)
    if ARTIFACTS[name].kind in ("list", "map"):
        assert payload == V1[name]
    else:
        assert {k: v for k, v in payload.items() if k not in ("schema_version", "artifact")} == V1[name]
    # and reading the v1 file gives the same payload
    v1_path = str(tmp_path / f"{name}.v1.json")
    with open(v1_path, "w", encoding="utf-8") as f:
        json.dump(V1[name], f)
    assert load_payload(name, v1_path) == payload


def test_envelope_shapes():
    assert set(to_v2("test_data", V1["test_data"])) == {"schema_version", "artifact", "datasets"}
    assert set(to_v2("scenario_element_map", V1["scenario_element_map"])) == {"schema_version", "artifact", "scenarios"}
    assert set(to_v2("test_plans", V1["test_plans"])) == {"schema_version", "artifact", "plans"}
    assert wrap("test_plans", wrap("test_plans", {})) == wrap("test_plans", {})


def test_missing_file_default_and_error(tmp_path):
    assert load_payload("test_plans", str(tmp_path / "none.json"), {}) == {}
    with pytest.raises(FileNotFoundError):
        load_payload("test_plans", str(tmp_path / "none.json"))
    assert load_records(str(tmp_path / "none.json")) == []


def test_newer_schema_version_is_refused():
    with pytest.raises(ArtifactVersionError):
        detect_version("test_suite", {"schema_version": 3, "specs": []})
    assert not validate_document("test_suite", {"schema_version": 3, "specs": []}).ok


@pytest.mark.parametrize("name,bad,needle", [
    ("test_data", {"not": "a list"}, "must be a JSON array"),
    ("test_data", [{"positive_dataset": []}], "scenario_id"),
    ("business_scenarios", {"scenarios": [{"title": "no id"}]}, "scenario_id"),
    ("test_plans", {"BS-1": {"tests": [{"name": "t", "steps": [{"locator_key": "x"}]}]}}, "action"),
    ("test_suite", {"specs": "nope"}, "specs"),
    ("scenario_element_map", {"BS-1": {"relevant_elements": "x"}}, "relevant_elements"),
    ("dom_elements", ["a", "list"], "JSON object"),
    ("locator_map", {"k": {"locator": "#x"}}, "type"),
    ("execution_results", {"results": [{"spec_file": "a"}]}, "status"),
])
def test_contract_violations_are_reported(name, bad, needle):
    report = validate_document(name, bad)
    assert not report.ok
    assert any(needle in e for e in report.errors), report.errors


def test_fallback_core_test_data_shape_is_canonicalised():
    from agents.common.fallback_core import fallback_generate_test_data

    legacy = fallback_generate_test_data([{"scenario_id": "BS-9", "title": "t", "steps": [{"description": "x"}]}])
    v2 = to_v2("test_data", legacy)
    assert validate_document("test_data", v2).ok
    ds = v2["datasets"][0]
    assert isinstance(ds["positive_dataset"], list)
    for variant in ds["negative_variants"]:
        assert "data" not in variant and isinstance(variant["iterations"], list)


def test_legacy_id_map_test_data_still_loads(tmp_path):
    path = tmp_path / "td.json"
    path.write_text(json.dumps({"BS-1": {"positive_dataset": []}}), encoding="utf-8")
    assert load_records(str(path)) == [{"positive_dataset": [], "scenario_id": "BS-1"}]


def test_atomic_write_leaves_no_temp_files(tmp_path):
    out_dir = tmp_path / "atomic"
    save_artifact("test_suite", str(out_dir / "test_suite.json"), {"specs": []})
    assert sorted(os.listdir(out_dir)) == ["test_suite.json"]


# ── Real project artifacts in this repo (acceptance: all validate or migrate) ─

def _real_artifacts():
    rows = []
    for root in ("application_assets/projects", "application_assets/myTestProjects"):
        base = os.path.join(REPO, root)
        if not os.path.isdir(base):
            continue
        for proj in sorted(os.listdir(base)):
            pdir = os.path.join(base, proj)
            if os.path.isdir(pdir):
                rows += [(name, path) for name, path in iter_project_artifacts(pdir)]
    return rows


REAL = _real_artifacts()


@pytest.mark.skipif(not REAL, reason="no project artifacts checked in")
@pytest.mark.parametrize("name,path", REAL, ids=[os.path.relpath(p, REPO) for _, p in REAL])
def test_every_existing_project_artifact_validates_or_migrates(name, path):
    report = validate_file(name, path)
    assert report.ok, report.errors


def test_real_artifacts_round_trip_through_v2():
    for name, path in REAL:
        if ARTIFACTS[name].kind == "plain":
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if name == "test_data":
            continue  # the old fallback shape is canonicalised on purpose (see migrations.py)
        v2 = to_v2(name, data)
        assert to_v2(name, to_v1(name, v2)) == v2, path       # lossless both ways
        if detect_version(name, data) == 1:
            assert to_v1(name, v2) == data, path               # v1 body preserved exactly


# ── Paths ─────────────────────────────────────────────────────────────────────

def test_legacy_comprehension_dir_is_found(tmp_path):
    legacy = tmp_path / "comprehension"
    legacy.mkdir()
    (legacy / "business_scenarios.json").write_text("{}", encoding="utf-8")
    assert artifact_path(str(tmp_path), "business_scenarios", existing_only=True).endswith(
        os.path.join("comprehension", "business_scenarios.json"))
    current = tmp_path / "test_comprehension"
    current.mkdir()
    (current / "business_scenarios.json").write_text("{}", encoding="utf-8")
    assert "test_comprehension" in artifact_path(str(tmp_path), "business_scenarios", existing_only=True)


# ── Schemas on disk are current ──────────────────────────────────────────────

def test_exported_schemas_are_up_to_date():
    from contracts.artifacts.export_schemas import main

    assert main(["--check", "--out", os.path.join(REPO, "schemas")]) == 0


def test_schemas_cover_every_artifact():
    from contracts.artifacts.export_schemas import build_schemas

    built = build_schemas()
    assert {s["x-mta-artifact"] for s in built.values()} == set(ARTIFACTS)


# ── Boundary enforcement ──────────────────────────────────────────────────────

def _project_with(tmp_path, rel, data):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(tmp_path)


def test_boundary_ok_and_missing_artifacts(tmp_path):
    pdir = _project_with(tmp_path, "test_creation/test_data/test_data.json", V1["test_data"])
    reports = validate_step_outputs(pdir, "testdata")
    assert len(reports) == 1 and reports[0].ok
    assert validate_step_outputs(pdir, "semantic_map") == []  # missing = not a violation
    out = apply_enforcement({"status": "success"}, reports, "warn")
    assert out["status"] == "success" and out["contract_checks"]["checked"] == 1


def test_boundary_warn_vs_block(tmp_path):
    pdir = _project_with(tmp_path, "test_creation/test_plans.json", {"BS-1": {"tests": "broken"}})
    reports = validate_step_outputs(pdir, "script_generation")
    warned = apply_enforcement({"status": "success"}, reports, "warn")
    assert warned["status"] == "partial" and warned["partial_reasons"][0].startswith("contract violation")
    blocked = apply_enforcement({"status": "success"}, reports, "block")
    assert blocked["status"] == "failed" and blocked["blocking"] is True


def test_boundary_dom_elements_in_module_and_legacy_dirs(tmp_path):
    _project_with(tmp_path, "test_comprehension/modules/M01/dom_elements.json", V1["dom_elements"])
    _project_with(tmp_path, "comprehension/dom_elements.json", V1["dom_elements"])
    reports = validate_step_outputs(str(tmp_path), "discovery")
    assert len(reports) == 2 and all(r.ok for r in reports)


def test_every_legacy_workflow_step_has_a_contract_mapping():
    import yaml

    for wf in ("full_workflow", "test_test_creation_only", "test_execution_and_healing", "healing_only"):
        with open(os.path.join(REPO, "workflows", f"{wf}.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        steps = [s if isinstance(s, str) else (s.get("name") or s.get("step") or s.get("agent"))
                 for s in data.get("steps", [])]
        for step in steps:
            assert step in STEP_ARTIFACTS, f"{wf}: step '{step}' has no contract mapping"
