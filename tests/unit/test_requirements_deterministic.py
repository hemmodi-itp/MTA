"""Phase 1.1 — deterministic pieces of requirement extraction: the declared-id parser, the atomicity check,
risk / priority / testability classification, stable id allocation and the requirements config block."""

import os

import pytest

from tools.requirements import atomicity, classify, explicit
from tools.requirements.config import requirements_enabled, resolve_requirements_config
from tools.requirements.ids import IdAllocator
from tools.state.artifact_registry import ArtifactRegistry

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUGGY_SHOP_BRD = os.path.join(ROOT, "benchmarks", "apps", "buggy_shop", "brd.md")


# ── explicit parser ──────────────────────────────────────────────────────────

def test_buggy_shop_brd_parses_8_requirements_27_criteria():
    reqs = explicit.parse(open(BUGGY_SHOP_BRD, encoding="utf-8").read())
    assert [r.id for r in reqs] == [f"REQ-0{i}" for i in range(1, 9)]
    assert sum(len(r.criteria) for r in reqs) == 27
    assert reqs[2].title == "Product management"
    assert reqs[2].description.startswith("Signed-in users can add, edit and delete products.")
    ac = reqs[2].criteria[1]
    assert ac.id == "AC-03.2" and ac.statement.startswith("Name must be 1–50 characters")


def test_wrapped_bullets_are_joined_and_paragraphs_end_them():
    text = "## REQ-7: Search\nIntro text.\n- AC-7.1: First line\n  continues here.\n\nUnrelated paragraph.\n"
    (req,) = explicit.parse(text)
    assert req.id == "REQ-7" and req.title == "Search" and req.description == "Intro text."
    assert req.criteria[0].statement == "First line continues here."


def test_criteria_without_a_heading_get_a_synthesised_requirement():
    (req,) = explicit.parse("Some prose\n* **AC-2.1** - The list paginates by 5.\n")
    assert req.id == "REQ-2" and req.synthesised and req.criteria[0].id == "AC-2.1"


def test_repeated_criterion_id_keeps_first_definition():
    text = "### REQ-1 A\n- AC-1.1: first\n### REQ-1 summary\n- AC-1.1: repeated\n"
    reqs = explicit.parse(text)
    assert [c.statement for r in reqs for c in r.criteria] == ["first"]


def test_no_declared_ids_gives_nothing():
    assert explicit.parse("# Shop\nUsers can log in. Users can search products.\n") == []


def test_custom_patterns():
    text = "FR-12 Login\n  FR-12.1 => valid users get in\n"
    pats = {"requirement": r"^(?P<id>FR-\d+)\s+(?P<text>.+)$",
            "criterion": r"^\s+(?P<id>FR-\d+\.\d+)\s*=>\s*(?P<text>.+)$"}
    # custom ids are parsed (normalisation to REQ/AC ids happens at merge time)
    reqs = explicit.parse(text, pats)
    assert reqs and reqs[0].id == "FR-12"


# ── atomicity ────────────────────────────────────────────────────────────────

ATOMIC = [
    "Given valid credentials, when the user submits the login form, then they land on the Products page.",
    "Name is required; an empty or blank name is rejected with \"Name is required\".",
    "The product list is paginated with 5 products per page, with Previous/Next links and a \"Page N of M\" indicator.",
    "Search matches any product whose name contains the search text, ignoring upper/lower case (for example \"mouse\" finds \"wireless Mouse\").",
    "A search containing any characters never causes an error; it simply returns the matching products or \"No products found\".",
    "The product description is shown on the product detail page as plain text: any HTML in it is displayed literally and never executed.",
    "Checkout with an empty cart does not create an order; the checkout page shows \"Your cart is empty\".",
    "Uploading a CSV or PNG file of at most 1 MB succeeds and shows \"Uploaded <file name>\".",
    "Every page has a \"Help\" link in the footer that opens the Help page.",
    "The product list loads within 2 seconds.",
]
COMPOUND = [
    ("Name must be 1–50 characters; a name of exactly 50 characters is accepted and 51 or more is rejected with \"Name must be at most 50 characters\".", "positive_and_negative"),
    ("Category must be one of Books or Home (\"Please choose a category\"); Description is at most 500 characters (\"Description must be at most 500 characters\").", "multiple_messages"),
    ("Any other file type is rejected with \"Only CSV or PNG files are allowed\"; files over 1 MB are rejected with \"File must be 1 MB or smaller\".", "multiple_messages"),
    ("Opening another user's order returns HTTP 403 with \"Access denied\". Administrators can see every order.", "positive_and_negative"),
    ("The Admin page is available only to administrators; any other signed-in user gets HTTP 403.", "positive_and_negative"),
    ("Quantity must be a whole number from 1 to 99 when adding from the product page; anything else is rejected with \"Quantity must be between 1 and 99\".", "multiple_conditions"),
    ("Discount code SAVE10 can be applied only once; applying it again shows \"Discount already applied\". Unknown codes show \"Invalid discount code\".", "multiple_messages"),
]


@pytest.mark.parametrize("statement", ATOMIC)
def test_single_behaviour_criteria_are_atomic(statement):
    assert atomicity.check(statement) == (True, [])


@pytest.mark.parametrize("statement,issue", COMPOUND)
def test_compound_criteria_are_flagged(statement, issue):
    atomic, issues = atomicity.check(statement)
    assert not atomic and issue in issues


def test_atomicity_never_raises_on_empty():
    assert atomicity.check("") == (True, [])
    assert atomicity.check(None) == (True, [])


# ── classification ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("When the user logs out, the session is invalidated", {"auth"}),
    ("Discount code SAVE10 gives 10% off the cart total", {"payment"}),
    ("When a product is deleted it disappears permanently", {"data-loss"}),
    ("The profile stores the user's email address and date of birth", {"PII"}),
    ("Every form field has an accessible name (WCAG 2.2 AA)", {"compliance"}),
    ("The product list is paginated with 5 products per page", set()),
    ("Sorting keeps the catalogue order", set()),
])
def test_risk_keyword_catalog(text, expected):
    assert set(classify.keyword_risk_tags(text)) == expected


def test_llm_risk_tags_are_filtered_to_the_enum():
    assert classify.risk_tags_for("plain text", ["auth", "Security", "pii", "data_loss"]) == ["auth", "data-loss", "PII"]


@pytest.mark.parametrize("text,expected", [
    ("Priority: P0 — users must sign in", "P0"), ("(P2) list paginates", "P2"), ("[P3] cosmetic", "P3"),
    ("MoSCoW: Must", "P1"), ("Priority: Should", "P2"), ("priority: could", "P3"), ("Priority: Won't", "P3"),
    ("the P1 model of the car is shown", None), ("no priority here", None),
])
def test_stated_priority(text, expected):
    assert classify.stated_priority(text) == expected


def test_priority_precedence_and_risk_floor():
    assert classify.resolve_priority("P3", "P0", []) == ("P3", "brd")
    assert classify.resolve_priority(None, "P0", []) == ("P0", "llm")
    assert classify.resolve_priority(None, "high", []) == ("P1", "llm")
    assert classify.resolve_priority(None, None, []) == ("P2", "default")
    assert classify.resolve_priority(None, "P3", ["payment"]) == ("P1", "rule")
    assert classify.resolve_priority(None, "P0", ["auth"]) == ("P0", "llm")      # floor never lowers
    assert classify.resolve_priority(None, None, ["PII"]) == ("P2", "default")   # PII has no floor


def test_agent_eval_priority_mapping():
    assert [classify.to_agent_eval_priority(p) for p in ("P0", "P1", "P2", "P3")] == ["high", "high", "medium", "low"]
    assert [classify.from_agent_eval_priority(p) for p in ("high", "medium", "low", None)] == ["P1", "P2", "P3", "P2"]


@pytest.mark.parametrize("text,expected", [
    ("The product list (page and API) loads within 2 seconds.", "non_functional"),
    ("Every field has a label programmatically associated with its input (accessible name).", "non_functional"),
    ("POST /api/products returns 422 with errors", "api"),
    ("The legal team manually reviews the terms", "manual_only"),
    ("The cart total is shown", "ui"),
])
def test_heuristic_testability(text, expected):
    assert classify.heuristic_testability(text)[0] == expected


def test_resolve_testability_prefers_valid_llm_value():
    assert classify.resolve_testability("api", "only via HTTP", "x")[:3:2] == ("api", "llm")
    assert classify.resolve_testability("not_testable", "", "the cart total is shown")[2] == "heuristic"  # no reason
    assert classify.resolve_testability("browser", "r", "the cart total is shown")[0] == "ui"            # not in enum


# ── ids ──────────────────────────────────────────────────────────────────────

def test_ids_are_stable_content_keyed_and_skip_document_numbers(tmp_path):
    alloc = IdAllocator(ArtifactRegistry(str(tmp_path)))
    first = alloc.requirement_id("Export", "Users export orders", taken_ids=["REQ-01", "REQ-02"])
    assert first == "REQ-003"
    assert alloc.requirement_id("Export", "Users export orders") == first          # same content, same id
    assert alloc.requirement_id("Import", "Users import orders") == "REQ-004"
    assert alloc.criterion_id("REQ-03", "a new behaviour", taken_ids=["AC-03.1", "AC-03.2"]) == "AC-03.3"
    assert alloc.child_id("AC-03.2", "50 accepted") == "AC-03.2.1"
    assert alloc.child_id("AC-03.2", "51 rejected") == "AC-03.2.2"
    assert alloc.test_case_id("M01", "M01_BS_001", "positive — login", "positive") == "M01_TC_001"
    alloc.save()
    again = IdAllocator(ArtifactRegistry(str(tmp_path)))                          # persisted across runs
    assert again.requirement_id("Import", "Users import orders") == "REQ-004"
    assert again.test_case_id("M01", "M01_BS_001", "positive — login", "positive") == "M01_TC_001"
    assert again.test_case_id("M01", "M01_BS_001", "negative — bad password", "negative") == "M01_TC_002"


# ── config ───────────────────────────────────────────────────────────────────

def test_requirements_config_defaults_and_validation():
    assert resolve_requirements_config({}) == {"enabled": False, "doc_id_patterns": {}}
    assert resolve_requirements_config({"requirements": {"enabled": "yes"}})["enabled"] is True
    cfg = resolve_requirements_config({"requirements": {"enabled": True, "doc_id_patterns": {
        "requirement": r"^(?P<id>FR-\d+) (?P<text>.*)$", "criterion": "([bad", "other": "x"}}})
    assert list(cfg["doc_id_patterns"]) == ["requirement"]      # invalid regex / unknown keys dropped


def test_requirements_enabled_request_wins_over_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.constants.PROJECTS_BASE", str(tmp_path))
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "project.yaml").write_text("requirements:\n  enabled: true\n", encoding="utf-8")
    assert requirements_enabled("p") is True
    assert requirements_enabled("p", {"requirements": {"enabled": False}}) is False
    assert requirements_enabled("missing") is False


def test_manifest_passes_requirements_block(tmp_path, monkeypatch):
    import tools.project_manifest as pm

    monkeypatch.setattr(pm, "_PROJECTS_DIR", str(tmp_path))
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "project.yaml").write_text("project:\n  name: p\nrequirements:\n  enabled: true\n",
                                                 encoding="utf-8")
    assert pm.load_project_manifest("p")["requirements"] == {"enabled": True, "doc_id_patterns": {}}
    (tmp_path / "p" / "project.yaml").write_text("project:\n  name: p\n", encoding="utf-8")
    assert pm.load_project_manifest("p")["requirements"]["enabled"] is False
