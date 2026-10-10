"""Phase 1.1 / 1.3 — scenario ↔ AC and test ↔ AC linking (validation, similarity backfill, inheritance)."""

from tools.requirements.linking import criteria_index, expand_to_leaves, link_scenario, link_scenarios, link_test
from tools.requirements.models import RequirementsDoc


def _ac(i, s, **kw):
    return {"id": i, "statement": s, "testability": "ui", "testability_reason": "r", "priority": "P2", **kw}


DOC = RequirementsDoc.model_validate({"requirements": [
    {"id": "REQ-01", "title": "Login", "module_id": "M01", "acceptance_criteria": [
        _ac("AC-01.1", "Given valid credentials the user lands on the Products page"),
        _ac("AC-01.2", "A wrong password shows exactly Invalid username or password"),
    ]},
    {"id": "REQ-03", "title": "Products", "module_id": "M03", "acceptance_criteria": [
        _ac("AC-03.2", "Name must be 1-50 characters", children=["AC-03.2.1", "AC-03.2.2"], atomic=False),
        _ac("AC-03.2.1", "a name of exactly 50 characters is accepted", parent_id="AC-03.2"),
        _ac("AC-03.2.2", "a name of 51 characters is rejected", parent_id="AC-03.2"),
    ]},
    {"id": "REQ-06", "title": "Orders", "module_id": "M04", "acceptance_criteria": [
        _ac("AC-06.2", "Opening another user's order returns HTTP 403 Access denied"),
    ]},
]})
INDEX = criteria_index(DOC)


def test_expand_to_leaves_validates_and_expands_parents():
    leaves, dropped = expand_to_leaves(["ac-01.2", "AC-03.2", "AC-99.9", "AC-01.2"], INDEX)
    assert leaves == ["AC-01.2", "AC-03.2.1", "AC-03.2.2"]
    assert dropped == ["AC-99.9"]


def test_llm_links_are_validated():
    sc = {"scenario_id": "M01_BS_001", "module_id": "M01", "ac_ids": ["AC-01.1", "AC-77.1"]}
    out = link_scenario(sc, DOC)
    assert out["ac_ids"] == ["AC-01.1"] and out["ac_link_source"] == "llm"


def test_similarity_backfill_within_module():
    sc = {"scenario_id": "M01_BS_002", "module_id": "M01", "title": "Failed login",
          "steps": ["enter a wrong password"], "expected_result": "Invalid username or password is shown"}
    out = link_scenario(sc, DOC)
    assert out["ac_ids"] == ["AC-01.2"] and out["ac_link_source"] == "similarity"


def test_requirement_hint_boosts_similarity():
    sc = {"scenario_id": "M01_BS_003", "module_id": "M01", "title": "Sign in", "steps": ["valid credentials"],
          "traceability": [{"requirement_id": "REQ-01"}]}
    assert "AC-01.1" in link_scenario(sc, DOC)["ac_ids"]


def test_cross_module_fallback_for_shared_sections():
    sc = {"scenario_id": "M06_BS_007", "module_id": "M06", "title": "Customer order visibility via API",
          "steps": ["open another user's order"], "expected_result": "HTTP 403 Access denied is returned"}
    assert link_scenario(sc, DOC)["ac_ids"] == ["AC-06.2"]


def test_unrelated_scenario_stays_unlinked():
    sc = {"scenario_id": "M01_BS_009", "module_id": "M01", "title": "Change the site theme",
          "steps": ["toggle dark mode"], "ac_ids": [], "ac_link_source": "llm"}
    out = link_scenario(sc, DOC)
    assert "ac_ids" not in out and "ac_link_source" not in out


def test_link_scenarios_noop_without_requirements():
    sc = [{"scenario_id": "x"}]
    assert link_scenarios(sc, None) is sc


def test_test_links_direct_similarity_inherited_unlinked():
    allowed = ["AC-03.2.1", "AC-03.2.2"]
    # direct: the plan's own ids, restricted to the scenario's ACs (a parent expands to its children)
    assert link_test({"name": "x", "ac_ids": ["AC-03.2", "AC-01.1"]}, allowed, INDEX) == (allowed, "direct")
    # similarity: no ids, but the test's own text matches one AC
    t = {"name": "boundary — name of 51 characters is rejected", "type": "boundary",
         "steps": [{"action": "enterText", "locator_key": "name_input", "value": "x" * 51}]}
    assert link_test(t, allowed, INDEX) == (["AC-03.2.2"], "similarity")
    # inherited: nothing points at a specific AC
    assert link_test({"name": "positive — open the form", "steps": []}, allowed, INDEX) == (allowed, "inherited")
    # unlinked: the scenario itself has no AC
    assert link_test({"name": "anything", "ac_ids": ["AC-03.2.1"]}, [], INDEX) == ([], "")
