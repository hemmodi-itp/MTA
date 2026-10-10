"""Phase 1.1 — extraction pipeline: declared criteria are authoritative, the LLM classifies / splits / adds but
can never drop, quotes are verified, splits are validated, cross-module id collisions are re-keyed, and an LLM
failure degrades instead of failing."""

import json

import pytest

from tools.requirements.extract import extract_requirements
from tools.requirements.ids import IdAllocator
from tools.requirements.models import RequirementsDoc
from tools.state.artifact_registry import ArtifactRegistry

BRD = """# Shop BRD

### REQ-03 Product management

Signed-in users can add, edit and delete products.

- AC-03.1: Name is required; an empty or blank name is rejected with "Name is required".
- AC-03.2: Name must be 1–50 characters; a name of exactly 50 characters is accepted and 51 or more is rejected with "Name must be at most 50 characters".

Deleting a product asks for confirmation before it is removed.
"""


class FakeLLM:
    """generate(prompt) -> canned JSON; records prompts."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r)


def _alloc(tmp_path):
    return IdAllocator(ArtifactRegistry(str(tmp_path)))


def _criteria(res):
    return {ac.id: ac for r in res.requirements for ac in r.acceptance_criteria}


LLM_OK = {"requirements": [{
    "id": "REQ-03", "title": "Product management", "priority": "P1",
    "acceptance_criteria": [
        {"id": "AC-03.1", "statement": "Name is required", "testability": "ui",
         "testability_reason": "form validation message", "priority": "P1", "risk_tags": []},
        {"id": "AC-03.2", "statement": "Name length", "testability": "ui", "testability_reason": "form",
         "priority": "P1", "risk_tags": [],
         "split": ["a name of exactly 50 characters is accepted",
                   "51 or more is rejected with \"Name must be at most 50 characters\""]},
        {"id": "", "statement": "Deleting a product asks for confirmation before it is removed.",
         "source_quote": "Deleting a product asks for confirmation before it is removed",
         "testability": "ui", "testability_reason": "confirmation dialog", "priority": "P2",
         "risk_tags": ["data-loss"]},
        {"id": "", "statement": "Products can be exported to Excel by admins.",
         "source_quote": "Admins can export products to Excel", "testability": "ui",
         "testability_reason": "x", "priority": "P3"},
    ]}]}


def test_full_merge(tmp_path):
    llm = FakeLLM(LLM_OK)
    res = extract_requirements(BRD, llm, allocator=_alloc(tmp_path), module_id="M03", module_label="M03 Products")
    assert res.status == "ok"
    acs = _criteria(res)
    # declared criteria keep their document id and document text (the LLM's paraphrase is ignored)
    assert acs["AC-03.1"].statement.startswith("Name is required; an empty or blank name")
    assert acs["AC-03.1"].quote_match == "exact" and acs["AC-03.1"].classification_source == "llm"
    assert acs["AC-03.1"].testability_reason == "form validation message"
    # the compound declared criterion was split into validated atomic children
    parent = acs["AC-03.2"]
    assert parent.children == ["AC-03.2.1", "AC-03.2.2"] and parent.atomic is False
    assert acs["AC-03.2.1"].parent_id == "AC-03.2" and acs["AC-03.2.1"].atomic
    # an undeclared criterion with a verified quote is added under its requirement with a generated id
    added = [a for a in acs.values() if a.doc_id is None and not a.parent_id]
    assert len(added) == 1 and added[0].id == "AC-03.3" and "data-loss" in added[0].risk_tags
    # a fabricated one is rejected and reported, never kept
    assert [r.reason for r in res.rejected] == ["quote_not_found"]
    assert "Excel" in res.rejected[0].statement
    # the whole result validates as a requirements document
    RequirementsDoc.model_validate({"requirements": [r.model_dump() for r in res.requirements]})
    # the prompt listed the declared criteria and fenced the BRD as untrusted
    assert "- AC-03.2 (REQ-03 Product management)" in llm.prompts[0]
    assert "<untrusted_content" in llm.prompts[0]


def test_llm_cannot_drop_declared_criteria(tmp_path):
    llm = FakeLLM({"requirements": [{"title": "Product management", "acceptance_criteria": [
        {"id": "AC-03.1", "statement": "x", "testability": "ui", "testability_reason": "r"}]}]})
    acs = _criteria(extract_requirements(BRD, llm, allocator=_alloc(tmp_path), module_id="M03"))
    assert {"AC-03.1", "AC-03.2"} <= set(acs)
    assert acs["AC-03.2"].classification_source == "heuristic"     # unclassified by the LLM → heuristic
    assert acs["AC-03.1"].classification_source == "llm"


def test_restated_declared_criterion_is_not_duplicated(tmp_path):
    llm = FakeLLM({"requirements": [{"id": "REQ-03", "title": "Product management", "acceptance_criteria": [
        {"id": "", "statement": "Name is required; an empty or blank name is rejected with \"Name is required\"",
         "testability": "ui", "testability_reason": "r"}]}]})
    acs = _criteria(extract_requirements(BRD, llm, allocator=_alloc(tmp_path), module_id="M03"))
    assert sorted(acs) == ["AC-03.1", "AC-03.2"]


def test_split_with_ungrounded_part_is_rejected(tmp_path):
    bad = json.loads(json.dumps(LLM_OK))
    bad["requirements"][0]["acceptance_criteria"][1]["split"] = [
        "a name of exactly 50 characters is accepted", "passwords expire after ninety days"]
    res = extract_requirements(BRD, FakeLLM(bad), allocator=_alloc(tmp_path), module_id="M03")
    acs = _criteria(res)
    assert acs["AC-03.2"].children == [] and acs["AC-03.2"].atomic is False
    kinds = {w.kind for w in res.warnings if w.id == "AC-03.2"}
    assert {"split_rejected", "non_atomic_not_split"} <= kinds


def test_invalid_llm_structure_gets_one_repair_retry(tmp_path):
    llm = FakeLLM({"requirements": [{"acceptance_criteria": []}]}, LLM_OK)   # first answer lacks "title"
    res = extract_requirements(BRD, llm, allocator=_alloc(tmp_path), module_id="M03")
    assert res.status == "ok" and len(llm.prompts) == 2
    assert "did not match the required structure" in llm.prompts[1]


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    import tools.requirements.extract as ex
    monkeypatch.setattr(ex, "TRANSIENT_RETRY_DELAY_S", 0)


def test_transient_connector_error_is_retried_once(tmp_path):
    llm = FakeLLM(ConnectionError("503"), LLM_OK)
    res = extract_requirements(BRD, llm, allocator=_alloc(tmp_path), module_id="M03")
    assert res.status == "ok" and len(llm.prompts) == 2


def test_llm_added_duplicate_of_another_module_is_not_re_added(tmp_path):
    other = {"AC-01.9": "Deleting a product asks for confirmation before it is removed."}
    res = extract_requirements(BRD, FakeLLM(LLM_OK), allocator=_alloc(tmp_path), module_id="M03", reserved=other)
    statements = [a.statement for a in _criteria(res).values()]
    assert not any(s.startswith("Deleting a product") for s in statements)
    assert any(w.kind == "duplicate_of_other_module" and w.id == "AC-01.9" for w in res.warnings)


@pytest.mark.parametrize("failure", [ConnectionError("network down"), "not json at all",
                                     {"requirements": [{"acceptance_criteria": []}]}])
def test_llm_failure_degrades_to_declared_criteria(tmp_path, failure):
    res = extract_requirements(BRD, FakeLLM(failure), allocator=_alloc(tmp_path), module_id="M03")
    assert res.status == "degraded"
    assert sorted(_criteria(res)) == ["AC-03.1", "AC-03.2"]
    assert all(a.classification_source == "heuristic" for a in _criteria(res).values())
    assert any("LLM call failed" in lim for lim in res.limitations)


def test_no_llm_and_no_declared_ids_fails_with_reason(tmp_path):
    res = extract_requirements("Users can log in. Users can log out.", None, allocator=_alloc(tmp_path))
    assert res.status == "failed" and res.requirements == []
    assert any("No requirements could be extracted" in lim for lim in res.limitations)


def test_undeclared_brd_extracts_llm_requirements_with_generated_ids(tmp_path):
    text = "The shop lets customers log in with a username and password. Wrong passwords show an error message."
    llm = FakeLLM({"requirements": [{"id": "", "title": "Login",
                                     "source_quote": "customers log in with a username and password",
                                     "acceptance_criteria": [
        {"statement": "Wrong passwords show an error message", "source_quote": "Wrong passwords show an error message",
         "testability": "ui", "testability_reason": "visible", "priority": "P1", "risk_tags": ["auth"]}]}]})
    res = extract_requirements(text, llm, allocator=_alloc(tmp_path), module_id="M01")
    (req,) = res.requirements
    assert req.id == "REQ-001" and req.doc_id is None
    assert req.acceptance_criteria[0].id == "AC-001.1"
    assert req.acceptance_criteria[0].risk_tags == ["auth"] and req.acceptance_criteria[0].priority == "P1"


def test_requirement_without_criteria_uses_its_verified_quote_not_the_llm_summary(tmp_path):
    text = "Accessibility: semantic HTML, labelled form controls, errors announced with role alert."
    llm = FakeLLM({"requirements": [{"title": "Accessibility",
                                     "description": "Accessibility guidelines for the storefront.",
                                     "source_quote": "semantic HTML, labelled form controls, errors announced with role alert",
                                     "acceptance_criteria": []}]})
    (req,) = extract_requirements(text, llm, allocator=_alloc(tmp_path)).requirements
    assert req.acceptance_criteria[0].statement == \
        "semantic HTML, labelled form controls, errors announced with role alert"


def test_same_statement_under_two_llm_requirements_is_kept_once(tmp_path):
    text = "Errors are announced with role alert. Every form control is labelled."
    crit = {"statement": "Errors are announced with role alert", "source_quote": "Errors are announced with role alert",
            "testability": "non_functional", "testability_reason": "a11y"}
    llm = FakeLLM({"requirements": [
        {"title": "Accessibility", "source_quote": "Errors are announced with role alert", "acceptance_criteria": [crit]},
        {"title": "Error handling", "source_quote": "Errors are announced with role alert",
         "acceptance_criteria": [{**crit, "statement": "Errors must be announced with role alert"}]}]})
    res = extract_requirements(text, llm, allocator=_alloc(tmp_path))
    assert len(_criteria(res)) == 1


def test_llm_claimed_ids_not_in_document_are_not_trusted(tmp_path):
    text = "Customers can log in with a username and password."
    llm = FakeLLM({"requirements": [{"id": "REQ-77", "title": "Login",
                                     "source_quote": "Customers can log in with a username and password",
                                     "acceptance_criteria": [{"id": "AC-77.1",
                                                              "statement": "Customers can log in with a username and password",
                                                              "testability": "ui", "testability_reason": "r"}]}]})
    (req,) = extract_requirements(text, llm, allocator=_alloc(tmp_path)).requirements
    assert req.id == "REQ-001" and req.acceptance_criteria[0].id == "AC-001.1"


def test_cross_module_id_collision_is_rekeyed(tmp_path):
    other = {"REQ-03": "Order history", "AC-03.1": "Customers see only their own orders"}
    res = extract_requirements(BRD, None, allocator=_alloc(tmp_path), module_id="M09", reserved=other)
    ids = sorted(_criteria(res))
    assert "AC-03.1" not in ids and res.requirements[0].id != "REQ-03"
    assert res.requirements[0].doc_id == "REQ-03"
    assert any(w.kind == "id_collision" for w in res.warnings)


def test_same_text_in_another_module_keeps_document_id(tmp_path):
    same = {"REQ-03": "Product management"}
    res = extract_requirements(BRD, None, allocator=_alloc(tmp_path), module_id="M09", reserved=same)
    assert res.requirements[0].id == "REQ-03"


def test_dom_inferred_source_caps_confidence(tmp_path):
    res = extract_requirements(BRD, FakeLLM(LLM_OK), allocator=_alloc(tmp_path), source="dom_inferred")
    assert all(a.source == "dom_inferred" and a.confidence <= 0.6 for a in _criteria(res).values())


def test_wont_priority_marks_not_testable(tmp_path):
    text = "### REQ-09 Wishlist\n- AC-09.1: Users can share wishlists (Priority: Won't).\n"
    (ac,) = _criteria(extract_requirements(text, None, allocator=_alloc(tmp_path))).values()
    assert ac.testability == "not_testable" and ac.priority == "P3" and ac.priority_source == "brd"


def test_long_brd_is_cut_with_limitation(tmp_path, monkeypatch):
    import tools.requirements.extract as ex

    monkeypatch.setattr(ex, "MAX_BRD_CHARS", 200)
    res = ex.extract_requirements(BRD, None, allocator=_alloc(tmp_path))
    assert any("longer than 200 characters" in lim for lim in res.limitations)
