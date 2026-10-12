"""Phase 1.2 — traceability.json: rebuild from artifacts, result updates, every "zero tests" reason, summary
maths, the report section and the I/O wrappers (no-ops when requirements.enabled is off)."""

import json
import os

import pytest

from contracts.artifacts import save_artifact
from tools.requirements import traceability as tr
from tools.requirements.models import RequirementsDoc


def _ac(i, testability="ui", **kw):
    return {"id": i, "statement": f"statement of {i}", "testability": testability,
            "testability_reason": kw.pop("reason", "r"), "priority": kw.pop("priority", "P2"), **kw}


def _doc():
    return RequirementsDoc.model_validate({"requirements": [
        {"id": "REQ-01", "title": "Login", "module_id": "M01", "acceptance_criteria": [
            _ac("AC-01.1", priority="P0"), _ac("AC-01.2"),
            _ac("AC-01.3", "manual_only", reason="needs a human"), _ac("AC-01.4", "non_functional"),
            _ac("AC-01.5", "api"), _ac("AC-01.6"), _ac("AC-01.7"), _ac("AC-01.8"), _ac("AC-01.9"),
            _ac("AC-01.10"), _ac("AC-01.11"), _ac("AC-01.12"),
        ]},
        {"id": "REQ-02", "title": "Form", "module_id": "M02", "acceptance_criteria": [
            _ac("AC-02.1", children=["AC-02.1.1", "AC-02.1.2"], atomic=False),
            _ac("AC-02.1.1", parent_id="AC-02.1"), _ac("AC-02.1.2", parent_id="AC-02.1"),
        ]},
        {"id": "REQ-03", "title": "Admin", "module_id": "M03", "acceptance_criteria": [_ac("AC-03.1")]},
        {"id": "REQ-04", "title": "Docs", "module_id": "M04", "acceptance_criteria": [_ac("AC-04.1")]},
    ]})


SCENARIOS = [
    {"scenario_id": "M01_BS_001", "module_id": "M01", "ac_ids": ["AC-01.1", "AC-01.2", "AC-01.12"]},
    {"scenario_id": "M01_BS_002", "module_id": "M01", "ac_ids": ["AC-01.6"]},    # safety drop
    {"scenario_id": "M01_BS_003", "module_id": "M01", "ac_ids": ["AC-01.7", "AC-01.2"]},   # missing locator
    {"scenario_id": "M01_BS_004", "module_id": "M01", "ac_ids": ["AC-01.8", "AC-01.2"]},   # placeholder dropped
    {"scenario_id": "M01_BS_005", "module_id": "M01", "ac_ids": ["AC-01.9", "AC-01.2"]},   # budget (capped)
    {"scenario_id": "M01_BS_006", "module_id": "M01", "ac_ids": ["AC-01.10"]},   # generation failed
    {"scenario_id": "M02_BS_001", "module_id": "M02", "ac_ids": ["AC-02.1.1", "AC-02.1.2"]},
    {"scenario_id": "M03_BS_001", "module_id": "M03", "ac_ids": ["AC-03.1"]},    # module not generated
    {"scenario_id": "M01_BS_007", "module_id": "M01", "title": "Change the colour theme"},   # no AC at all
]
PLANS = {
    "M01_BS_001": {"tests": [
        {"name": "positive — login", "type": "positive", "tc_id": "M01_TC_001", "ac_ids": ["AC-01.1"],
         "ac_link": "direct", "title": "AC-01.1 positive — login", "steps": []},
        {"name": "negative — wrong password", "type": "negative", "tc_id": "M01_TC_002",
         "ac_ids": ["AC-01.2"], "ac_link": "similarity", "title": "AC-01.2 negative — wrong password", "steps": []},
    ]},
    "M01_BS_007": {"tests": [{"name": "positive — theme", "type": "positive", "tc_id": "M01_TC_003", "ac_ids": [],
                              "ac_link": None, "title": "positive — theme", "steps": []}]},
    "M01_BS_002": {"tests": [{"name": "t", "tc_id": "M01_TC_004", "ac_ids": ["AC-01.6"], "ac_link": "direct",
                              "title": "AC-01.6 t", "steps": []}],
                   "dropped_for_safety": [{"test": "delete account"}]},
    "M01_BS_003": {"tests": [{"name": "t3", "tc_id": "M01_TC_005", "ac_ids": ["AC-01.2"], "ac_link": "direct",
                              "title": "t3", "steps": []}],
                   "missing_locators": ["pay_button"]},
    "M01_BS_004": {"tests": [{"name": "t4", "tc_id": "M01_TC_006", "ac_ids": ["AC-01.2"], "ac_link": "direct",
                              "title": "t4", "steps": []}],
                   "dropped_tests": [{"test": "negative — x", "reason": "placeholder_negative_dropped"}]},
    "M01_BS_005": {"tests": [{"name": "t5", "tc_id": "M01_TC_007", "ac_ids": ["AC-01.2"], "ac_link": "direct",
                              "title": "t5", "steps": []}]},
    "M02_BS_001": {"tests": [
        {"name": "boundary — 50 ok", "type": "boundary", "tc_id": "M02_TC_001", "ac_ids": ["AC-02.1.1"],
         "ac_link": "direct", "title": "AC-02.1.1 boundary — 50 ok", "steps": []}]},
}
SUITE = [
    {"spec_id": "M01_BS_001", "module_id": "M01", "file": "M01/test_M01_BS_001_login.spec.ts"},
    {"spec_id": "M01_BS_002", "module_id": "M01", "file": "M01/test_M01_BS_002.spec.ts"},
    {"spec_id": "M01_BS_003", "module_id": "M01", "file": "M01/test_M01_BS_003.spec.ts"},
    {"spec_id": "M01_BS_004", "module_id": "M01", "file": "M01/test_M01_BS_004.spec.ts"},
    {"spec_id": "M01_BS_005", "module_id": "M01", "file": "M01/test_M01_BS_005.spec.ts"},
    {"spec_id": "M02_BS_001", "module_id": "M02", "file": "M02/test_M02_BS_001.spec.ts"},
    {"spec_id": "M01_BS_007", "module_id": "M01", "file": "M01/test_M01_BS_007.spec.ts"},
]
TEST_DATA = [{"scenario_id": "M01_BS_005", "capped_variants": {"negative": 2}}]


@pytest.fixture
def trace():
    return tr.build(_doc(), SCENARIOS, PLANS, SUITE, TEST_DATA, no_url_modules=["M04"], project="p")


def test_tests_and_links(trace):
    assert set(trace.tests) == {"M01_TC_001", "M01_TC_002", "M01_TC_003", "M01_TC_004", "M01_TC_005",
                                "M01_TC_006", "M01_TC_007", "M02_TC_001"}
    t = trace.tests["M01_TC_002"]
    assert (t.spec_file, t.test_title, t.link, t.ac_ids) == (
        "M01/test_M01_BS_001_login.spec.ts", "AC-01.2 negative — wrong password", "similarity", ["AC-01.2"])
    assert trace.tests["M01_TC_001"].latest_result.status == "not_run"
    assert trace.unlinked_tests == ["M01_TC_003"]


@pytest.mark.parametrize("ac_id,code", [
    ("AC-01.3", "manual_only"),
    ("AC-01.4", "not_supported:non_functional"),
    ("AC-01.5", "not_supported:api"),
    ("AC-01.6", None),                          # covered (the remaining test still links to it)
    ("AC-01.7", "missing_locator"),
    ("AC-01.8", "placeholder_negative_dropped"),
    ("AC-01.9", "budget"),
    ("AC-01.10", "generation_failed"),
    ("AC-01.11", "no_scenario"),
    ("AC-01.12", "no_test_targets_ac"),
    ("AC-03.1", "module_not_generated"),
    ("AC-04.1", "no_url"),
])
def test_every_uncovered_reason(trace, ac_id, code):
    reason = trace.acs[ac_id].uncovered_reason
    assert (reason.code if reason else None) == code


def test_safety_drop_reason_when_nothing_left():
    plans = {**PLANS, "M01_BS_002": {**PLANS["M01_BS_002"], "tests": []}}
    t = tr.build(_doc(), SCENARIOS, plans, SUITE, TEST_DATA)
    assert t.acs["AC-01.6"].uncovered_reason.code == "dropped_for_safety"


def test_manual_reason_carries_testability_reason(trace):
    assert trace.acs["AC-01.3"].uncovered_reason.detail == "needs a human"


def test_split_parent_is_partial_until_all_children_covered(trace):
    parent = trace.acs["AC-02.1"]
    assert parent.status == "partial" and parent.uncovered_reason.code == "children_uncovered"
    assert parent.uncovered_reason.detail == "AC-02.1.2"
    assert parent.tc_ids == ["M02_TC_001"]


def test_legacy_specs_are_traced_through_their_scenario():
    plans = {"M01_BS_001": {"tests": [{"name": "positive — login", "type": "positive", "steps": []}]}}
    t = tr.build(_doc(), SCENARIOS, plans, SUITE)
    (tc_id, test), = t.tests.items()
    assert tc_id == "M01_BS_001#1" and test.link == "legacy"
    assert test.test_title == "positive — login @smoke"           # the title the untraced renderer emits
    assert test.ac_ids == ["AC-01.1", "AC-01.2", "AC-01.12"]


def test_scenario_linked_late_traces_its_already_generated_tests():
    """A test generated while its scenario had no AC (the criterion came from a later module) is linked at
    rebuild time — the scenario is re-linked project-wide in memory, then the test by similarity/inheritance."""
    doc = RequirementsDoc.model_validate({"requirements": [{"id": "REQ-07", "title": "Admin", "module_id": "M06",
        "acceptance_criteria": [_ac("AC-07.1", statement="The Admin page is available only to administrators")]}]})
    scenarios = [{"scenario_id": "M01_BS_005", "module_id": "M01", "title": "Admin page access",
                  "steps": ["open the Admin page as an administrator"], "expected_result": "available"}]
    plans = {"M01_BS_005": {"tests": [{"name": "positive — admin opens the page", "tc_id": "M01_TC_006",
                                       "ac_ids": [], "ac_link": None, "title": "positive — admin", "steps": []}]}}
    suite = [{"spec_id": "M01_BS_005", "module_id": "M01", "file": "M01/x.spec.ts"}]
    t = tr.build(doc, scenarios, plans, suite)
    assert t.tests["M01_TC_006"].ac_ids == ["AC-07.1"] and t.unlinked_tests == []
    assert t.acs["AC-07.1"].status == "covered"


def test_unrendered_plans_are_not_tests():
    t = tr.build(_doc(), SCENARIOS, {"M01_BS_006": {"tests": [{"name": "x", "tc_id": "M01_TC_099"}]}}, SUITE)
    assert "M01_TC_099" not in t.tests


def test_summary_counts(trace):
    s = trace.summary
    assert s["acs_total"] == 16                    # leaves only: 12 + 2 children + 1 + 1 (the parent is not counted)
    assert s["acs_automatable"] == 15              # everything except the manual_only AC
    assert s["acs_covered"] == 4                   # AC-01.1, AC-01.2, AC-01.6, AC-02.1.1
    assert s["coverage_pct"] == round(100 * 4 / 15, 1)
    assert s["by_reason"]["no_scenario"] == 1 and "children_uncovered" not in s["by_reason"]
    assert s["test_links"] == {"direct": 6, "similarity": 1, "unlinked": 1}
    assert s["non_atomic_parents"] == 1


def test_apply_results_by_annotation_then_title(trace):
    results = [
        {"spec_file": "x", "test_title": "renamed", "tc_id": "M01_TC_001", "status": "success", "pw_status": "expected"},
        {"spec_file": "application_assets/projects/p/test_creation/test_scripts/M01/test_M01_BS_001_login.spec.ts",
         "test_title": "AC-01.2 negative — wrong password", "status": "failed", "pw_status": "unexpected",
         "errors": ["\x1b[31mError: expect(locator).toHaveText()\x1b[39m\n  more lines"]},
        {"spec_file": "M02/test_M02_BS_001.spec.ts", "test_title": "AC-02.1.1 boundary — 50 ok",
         "status": "failed", "pw_status": "skipped"},
        {"spec_file": "elsewhere.spec.ts", "test_title": "unknown", "status": "success"},
    ]
    trace, unmatched = tr.apply_results(trace, results, run="20261011T000000Z")
    assert unmatched == 1
    assert trace.tests["M01_TC_001"].latest_result.status == "passed"
    failed = trace.tests["M01_TC_002"].latest_result
    assert failed.status == "failed" and failed.last_failure == "Error: expect(locator).toHaveText()"
    # Playwright "skipped" stays skipped even though UIExecution's own status says failed (design D6)
    assert trace.tests["M02_TC_001"].latest_result.status == "skipped"
    assert trace.acs["AC-01.1"].result == "passed" and trace.acs["AC-01.2"].result == "failed"
    assert trace.acs["AC-02.1"].result == "skipped"
    assert trace.summary["acs_passing"] == 1 and trace.summary["unmatched_results"] == 1


@pytest.mark.parametrize("statuses,expected", [
    ([], "not_run"), (["not_run"], "not_run"), (["passed", "passed"], "passed"), (["passed", "failed"], "mixed"),
    (["failed", "not_run"], "failed"), (["skipped"], "skipped"), (["passed", "skipped"], "mixed"),
])
def test_result_aggregation(statuses, expected):
    assert tr._aggregate_result(statuses) == expected


@pytest.mark.parametrize("r,expected", [
    ({"pw_status": "expected", "status": "failed"}, "passed"), ({"pw_status": "flaky"}, "flaky"),
    ({"pw_status": "timedOut"}, "failed"), ({"pw_status": "skipped", "status": "failed"}, "skipped"),
    ({"status": "success"}, "passed"), ({"status": "skipped"}, "skipped"), ({"status": "weird"}, "failed"),
])
def test_result_status_mapping(r, expected):
    assert tr.result_status(r) == expected


def test_rebuild_keeps_previous_results(trace):
    trace, _ = tr.apply_results(trace, [{"tc_id": "M01_TC_001", "pw_status": "expected"}])
    again = tr.build(_doc(), SCENARIOS, PLANS, SUITE, TEST_DATA, previous=trace)
    assert again.tests["M01_TC_001"].latest_result.status == "passed"
    assert again.acs["AC-01.1"].result == "passed"


def test_report_section(trace):
    sec = tr.report_section(trace)
    ids = [a["id"] for a in sec["acs"]]
    assert ids.index("AC-01.2") < ids.index("AC-01.10") < ids.index("AC-02.1") < ids.index("AC-02.1.1")
    uncovered = {u["id"]: u["code"] for u in sec["uncovered"]}
    assert uncovered["AC-01.11"] == "no_scenario" and "AC-02.1" not in uncovered and "AC-01.1" not in uncovered
    assert [u["tc_id"] for u in sec["unlinked_tests"]] == trace.unlinked_tests
    json.dumps(sec)   # serialisable for the JSON report


# ── I/O wrappers ─────────────────────────────────────────────────────────────

def _project(tmp_path, monkeypatch, enabled=True):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    p = tmp_path / "p"
    (p / "test_comprehension").mkdir(parents=True)
    (p / "test_creation").mkdir()
    (p / "project.yaml").write_text(
        f"project:\n  name: p\nmodules:\n  - id: M01\n    url: https://shop.test/m1\n"
        f"requirements:\n  enabled: {'true' if enabled else 'false'}\n", encoding="utf-8")
    save_artifact("requirements", str(p / "test_comprehension" / "requirements.json"),
                  _doc().model_dump(mode="json"))
    save_artifact("business_scenarios", str(p / "test_comprehension" / "business_scenarios.json"),
                  {"project": "p", "scenarios": SCENARIOS})
    save_artifact("test_plans", str(p / "test_creation" / "test_plans.json"), PLANS)
    save_artifact("test_suite", str(p / "test_creation" / "test_suite.json"), {"specs": SUITE})
    return p


def test_refresh_and_apply_for_project(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    trace = tr.refresh_project("p")
    assert trace is not None and os.path.exists(p / "test_creation" / "traceability.json")
    # modules without any URL in project.yaml are reported as no_url
    assert trace.acs["AC-03.1"].uncovered_reason.code == "no_url"
    updated = tr.apply_results_for_project("p", [{"tc_id": "M01_TC_001", "pw_status": "expected"}], run="r1")
    assert updated.tests["M01_TC_001"].latest_result.run == "r1"
    assert tr.load_traceability("p").tests["M01_TC_001"].latest_result.status == "passed"


def test_wrappers_are_noops_when_disabled(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch, enabled=False)
    assert tr.refresh_project("p") is None
    assert tr.apply_results_for_project("p", [{"tc_id": "M01_TC_001"}]) is None
    assert not os.path.exists(p / "test_creation" / "traceability.json")


def test_wrappers_are_noops_without_requirements(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    os.remove(p / "test_comprehension" / "requirements.json")
    assert tr.refresh_project("p") is None
