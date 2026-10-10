"""Phase 1 — benchmark support: acs.yaml ground truth, the AC-extraction recall scorer (text matching, id
stripping), and AC coverage from traceability links (children roll up; direct-only coverage)."""

import json
import os

from tools.benchmark.ac_recall import match_score, score_recall, strip_ids
from tools.benchmark.apps import APPS, load_ac_truth, load_acs
from tools.benchmark.score import ac_links

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_acs_yaml_covers_every_brd_criterion_verbatim():
    app = APPS["buggy_shop"]
    truth = load_ac_truth(app)
    assert sorted(t["id"] for t in truth) == load_acs(app)            # 27 ids, same as the BRD
    brd = open(app.brd_path, encoding="utf-8").read()
    for t in truth:
        assert t["statement"][:60] in brd.replace("\n", " ")
        assert t["testability"] in ("ui", "api", "non_functional", "manual_only", "not_testable")
        assert t["priority"] in ("P0", "P1", "P2", "P3")
        assert t["atomic"] or len(t["checks"]) >= 2
        assert t["module"] in app.module_reqs and t["req"] in app.module_reqs[t["module"]]


def test_strip_ids_removes_every_declared_id():
    text = strip_ids(open(APPS["buggy_shop"].brd_path, encoding="utf-8").read())
    assert "REQ-0" not in text and "AC-0" not in text
    assert "### Authentication and session" in text
    assert "- Given valid credentials" in text


def _gt(i, s, module="M01", **kw):
    return {"id": i, "module": module, "statement": s, "testability": "ui", "priority": "P1",
            "risk_tags": [], "atomic": True, **kw}


GT = [_gt("AC-01.1", "Given valid credentials, when the user submits the login form, then they land on the Products page."),
      _gt("AC-01.2", 'A wrong password shows exactly "Invalid username or password".'),
      _gt("AC-02.6", "The product list (page and API) loads within 2 seconds.", module="M02")]


def test_recall_matches_by_text_not_id():
    extracted = {
        "M01": [{"id": "AC-001.1", "statement": "Valid credentials land the user on the Products page",
                 "source_quote": "they land on the Products page", "testability": "ui", "priority": "P0"},
                {"id": "AC-009.9", "statement": "Passwords expire after 90 days", "testability": "ui"}],
        "M02": [{"id": "AC-02.1.1", "parent_id": "AC-02.1", "statement": "the product list is paginated by 5"},
                {"id": "AC-07.7", "statement": "The product list (page and API) loads within 2 seconds.",
                 "testability": "non_functional", "priority": "P2"}],
    }
    r = score_recall(GT, extracted)
    assert (r["extracted"], r["total"], r["missed"]) == (2, 3, ["AC-01.2"])
    rows = {row["id"]: row for row in r["rows"]}
    assert rows["AC-01.1"]["matched_id"] == "AC-001.1"
    assert rows["AC-02.6"]["matched_id"] == "AC-07.7"            # best match, not the first above threshold
    assert rows["AC-01.1"]["priority"] == ["P1", "P0"]
    assert r["agreement"]["testability"] == 0.5 and r["unmatched_extractions"] == 2


def test_recall_falls_back_project_wide():
    r = score_recall([GT[1]], {"M04": [{"id": "x", "statement": 'A wrong password shows exactly "Invalid username or password"'}]})
    assert r["recall"] == 1.0


def test_fabricated_extraction_does_not_match():
    assert match_score(GT[0]["statement"], {"statement": "Admins can export orders to Excel"}) < 0.7


def test_ac_links_roll_children_up_and_direct_only():
    assert ac_links({"ac_ids": ["AC-03.2.1", "AC-03.2.2", "AC-01.1"]}) == ["AC-01.1", "AC-03.2"]
    assert ac_links({"ac_ids": ["AC-01.1"], "ac_link": "inherited"}, direct_only=True) == []
    assert ac_links({"ac_ids": ["AC-01.1"], "ac_link": "similarity"}, direct_only=True) == ["AC-01.1"]
    assert ac_links({"title": "covers AC-05.2"}, direct_only=True) == []
    assert ac_links({"title": "covers AC-05.2"}) == ["AC-05.2"]


def test_test_inventory_uses_traceability_links(tmp_path):
    from contracts.artifacts import save_artifact
    from tools.benchmark.run import test_inventory

    pdir = tmp_path / "bench"
    (pdir / "test_creation").mkdir(parents=True)
    (pdir / "test_comprehension").mkdir()
    save_artifact("test_suite", str(pdir / "test_creation" / "test_suite.json"),
                  {"specs": [{"spec_id": "M01_BS_001", "file": "M01/test_M01_BS_001_login.spec.ts"}]})
    save_artifact("business_scenarios", str(pdir / "test_comprehension" / "business_scenarios.json"),
                  {"scenarios": [{"scenario_id": "M01_BS_001", "ac_ids": ["AC-01.1", "AC-01.2"]}]})
    save_artifact("traceability", str(pdir / "test_creation" / "traceability.json"), {"tests": {
        "M01_TC_001": {"spec_file": "M01/test_M01_BS_001_login.spec.ts", "test_title": "AC-01.2 neg",
                       "ac_ids": ["AC-01.2"], "link": "direct"}}})
    results = [
        {"spec_file": "x/M01/test_M01_BS_001_login.spec.ts", "test_title": "AC-01.2 neg", "tc_id": "M01_TC_001"},
        {"spec_file": "x/M01/test_M01_BS_001_login.spec.ts", "test_title": "AC-01.2 neg"},
        {"spec_file": "x/M01/test_M01_BS_001_login.spec.ts", "test_title": "legacy @smoke"},
    ]
    inv = test_inventory(str(pdir), results)
    assert [(i["ac_ids"], i["ac_link"]) for i in inv] == [
        (["AC-01.2"], "direct"), (["AC-01.2"], "direct"), (["AC-01.1", "AC-01.2"], "inherited")]


def test_scorer_reports_direct_coverage_and_recall():
    from tools.benchmark.score import score

    run = {"app": "x", "clean_runs": [{"t1": "passed", "t2": "passed"}], "bug_runs": {},
           "tests": [{"id": "t1", "ac_ids": ["AC-01.1"], "ac_link": "direct"},
                     {"id": "t2", "ac_ids": ["AC-01.2"], "ac_link": "inherited"}],
           "ac_extraction": {"recall": 0.963}}
    m = score(run, [], ["AC-01.1", "AC-01.2", "AC-01.3"])
    cov = m["requirement_coverage"]
    assert cov["covered"] == ["AC-01.1", "AC-01.2"] and cov["covered_direct"] == ["AC-01.1"]
    assert round(cov["direct_pct"], 4) == 0.3333 and m["ac_extraction_recall"] == 0.963
    from tools.benchmark.report_md import render_markdown
    assert m.get("llm") is not None
    md = render_markdown(m, {"date": "d"})
    assert "AC coverage, direct links only" in md and "AC extraction recall" in md
