"""Phase 0.3 — benchmark scorer (synthetic results), BRD split, materialisation,
app-server env isolation, Markdown report."""

import json
import os

import pytest
import yaml

from tools.benchmark.score import (
    ac_links,
    detect_bugs,
    flaky_tests,
    llm_cost,
    normalize_status,
    score,
)

pytestmark = pytest.mark.mta

BUGS = [
    {"id": "BUG_01", "category": "validation_boundary", "severity": "medium", "affected_ac": "AC-03.2", "how_detectable": "bva"},
    {"id": "BUG_02", "category": "server_client_mismatch", "severity": "high", "affected_ac": "AC-03.3", "how_detectable": "api"},
    {"id": "BUG_03", "category": "calculation", "severity": "high", "affected_ac": "AC-05.2", "how_detectable": "ui"},
    {"id": "BUG_04", "category": "calculation", "severity": "low", "affected_ac": "AC-05.3", "how_detectable": "ui"},
]
ACS = ["AC-01.1", "AC-03.2", "AC-03.3", "AC-05.2"]

TESTS = [
    {"id": "a", "title": "AC-03.2 name of 50 chars accepted"},
    {"id": "b", "title": "cart total", "text": "Traceability: AC-05.2"},
    {"id": "c", "title": "always red"},
    {"id": "d", "title": "wobbly", "ac_ids": ["AC-01.1"]},
    {"id": "e", "title": "skipped one", "ac_ids": ["AC-03.3"]},
]


def _record(**kw):
    rec = {
        "app": "buggy_shop",
        "tests": TESTS,
        "clean_runs": [
            {"a": "passed", "b": "passed", "c": "failed", "d": "passed", "e": "skipped"},
            {"a": "success", "b": "passed", "c": "failed", "d": "failed", "e": "skipped"},
        ],
        "bug_runs": {
            "BUG_01": {"a": "failed", "b": "passed", "c": "failed", "d": "passed"},   # caught by a
            "BUG_02": {"a": "passed", "b": "passed", "c": "failed", "d": "passed"},   # missed (c fails anyway)
            "BUG_03": {"a": "passed", "b": "failed", "c": "failed", "d": "failed"},   # caught by b only (d is flaky)
        },
        "bug_run_errors": {"BUG_04": "app crashed"},
        "heals": {"applied": 4, "wrong": 1},
        "runtime_s": {"generation": 100.0, "executions": [10, 12, 14], "total": 200.0},
        "llm_usage": {"gemini/g-1": {"calls": 3, "cache_hits": 1, "input_tokens": 2_000_000, "output_tokens": 500_000}},
    }
    rec.update(kw)
    return rec


def test_detection_only_counts_stable_passing_tests():
    m = score(_record(), BUGS, ACS)
    det = m["seeded_bug_detection"]
    by_id = {b["id"]: b for b in det["bugs"]}
    assert by_id["BUG_01"]["caught_by"] == ["a"]
    assert by_id["BUG_02"]["caught"] is False          # only the always-failing test failed
    assert by_id["BUG_03"]["caught_by"] == ["b"]        # flaky d is excluded
    assert by_id["BUG_04"]["evaluated"] is False and by_id["BUG_04"]["note"] == "app crashed"
    assert (det["caught"], det["evaluated"], det["enabled"]) == (2, 3, 4)
    assert det["rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert det["not_evaluated"] == ["BUG_04"]
    assert det["by_category"]["calculation"] == {"enabled": 1, "caught": 1}


def test_false_failure_and_flaky_rates():
    m = score(_record(), BUGS, ACS)
    assert m["tests_executed"] == 4                     # skipped e excluded
    assert m["false_failure"] == {"rate": 0.25, "failing_tests": ["c"]}
    assert m["flaky"]["tests"] == ["d"] and m["flaky"]["rate"] == 0.25
    assert score(_record(clean_runs=[_record()["clean_runs"][0]]), BUGS, ACS)["flaky"]["rate"] is None


def test_requirement_coverage_uses_links_and_ignores_skipped():
    cov = score(_record(), BUGS, ACS)["requirement_coverage"]
    assert cov["covered"] == ["AC-01.1", "AC-03.2", "AC-05.2"]
    assert cov["uncovered"] == ["AC-03.3"]               # its only test was skipped
    assert cov["pct"] == 0.75


def test_coverage_note_when_v1_tests_link_nothing():
    rec = _record(tests=[{"id": t, "title": "no ids"} for t in "abcd"])
    cov = score(rec, BUGS, ACS)["requirement_coverage"]
    assert cov["pct"] == 0.0 and "v1 artifacts" in cov["note"]


def test_heal_precision_and_runtime_and_cost():
    m = score(_record(), BUGS, ACS, pricing={"g-1": {"input_per_mtok": 0.5, "output_per_mtok": 2.0}})
    assert m["heal_precision"] == {"precision": 0.75, "applied": 4, "wrong": 1, "measured": True}
    assert m["runtime_s"]["execution_median"] == 12 and m["runtime_s"]["generation"] == 100.0
    assert m["llm"]["cost_usd"] == pytest.approx(2.0)
    assert m["llm"]["cache_hits"] == 1


def test_unpriced_models_give_null_cost_never_a_guess():
    m = score(_record(), BUGS, ACS, pricing={})
    assert m["llm"]["cost_usd"] is None and m["llm"]["unpriced_models"] == ["gemini/g-1"]
    assert llm_cost({"x/m": {"calls": 1, "cache_hits": 1, "input_tokens": 0, "output_tokens": 0}}, {})["cost_usd"] == 0.0


def test_no_heals_and_empty_runs():
    m = score(_record(heals=None, bug_runs={}, clean_runs=[]), BUGS, ACS)
    assert m["heal_precision"]["precision"] is None and m["heal_precision"]["measured"] is False
    assert m["seeded_bug_detection"]["rate"] is None
    assert m["false_failure"]["rate"] is None
    assert detect_bugs([], {"BUG_01": {"a": "failed"}}) == {"BUG_01": []}


def test_unknown_bug_ids_reported():
    rec = _record(bug_runs={"BUG_99": {"a": "failed"}})
    assert score(rec, BUGS, ACS)["unknown_bug_ids"] == ["BUG_99"]


@pytest.mark.parametrize("raw,expected", [
    ("passed", "passed"), ("expected", "passed"), ("flaky", "passed"), ("success", "passed"),
    ("failed", "failed"), ("timedOut", "failed"), ("unexpected", "failed"), ("weird", "failed"),
    ("skipped", "skipped"), ("", "skipped"), (None, "skipped"),
])
def test_normalize_status(raw, expected):
    assert normalize_status(raw) == expected


def test_ac_links_prefers_explicit_ids():
    assert ac_links({"ac_ids": ["AC-02.1"], "title": "AC-09.9"}) == ["AC-02.1"]
    assert ac_links({"title": "x AC-01.2 and AC-01.2 y", "text": "AC-03.1"}) == ["AC-01.2", "AC-03.1"]
    assert ac_links({"title": "AC-1"}) == []


def test_flaky_ignores_skips():
    runs = [{"a": "passed", "b": "skipped"}, {"a": "passed", "b": "passed"}]
    assert flaky_tests(runs) == []


def test_markdown_report_renders_key_rows():
    from tools.benchmark.report_md import render_markdown

    md = render_markdown(score(_record(), BUGS, ACS), {"date": "2026-10-10", "commit": "abc", "label": "t",
                                                         "notes": ["a note"]})
    assert "**66.7%**" in md and "| BUG_04 |" in md and "not run" in md
    assert "Cost not computed" in md and "> a note" in md


# ── materialisation / BRD split ──────────────────────────────────────────────

def test_split_brd_keeps_preamble_and_tail():
    from tools.benchmark.materialize import split_brd

    brd = "# T\n\nintro\n\n### REQ-01 A\n- AC-01.1: x\n\n### REQ-02 B\n- AC-02.1: y\n\n## 5. NFR\nfast\n"
    out = split_brd(brd, {"M01": ["REQ-01"], "M02": ["REQ-02"], "MX": ["REQ-01", "REQ-02"]})
    assert "intro" in out["M01"] and "AC-01.1" in out["M01"] and "AC-02.1" not in out["M01"]
    assert "AC-02.1" in out["M02"] and "## 5. NFR" in out["M02"] and "## 5. NFR" in out["M01"]
    assert out["MX"].count("### REQ-") == 2
    with pytest.raises(ValueError):
        split_brd(brd, {"M9": ["REQ-77"]})


def test_materialize_buggy_shop_project(tmp_path):
    from tools.benchmark.apps import APPS, load_acs, load_bugs
    from tools.benchmark.materialize import materialize_project

    app = APPS["buggy_shop"]
    pdir = materialize_project(app, str(tmp_path), "http://127.0.0.1:8765")
    cfg = yaml.safe_load(open(os.path.join(pdir, "project.yaml"), encoding="utf-8"))
    assert cfg["environment"] == "local" and cfg["contracts"]["enforce"] == "block"
    assert {m["url"].split("/")[2] for m in cfg["modules"]} == {"127.0.0.1:8765"}
    for m in cfg["modules"]:
        brd = open(os.path.join(pdir, "inputs", m["brd_file"]), encoding="utf-8").read()
        assert "### REQ-" in brd
    # every AC referenced by the ground truth exists in some module BRD
    all_brd = "".join(open(os.path.join(pdir, "inputs", f), encoding="utf-8").read()
                      for f in os.listdir(os.path.join(pdir, "inputs")))
    for bug in load_bugs(app):
        assert bug["affected_ac"] in all_brd
    assert len(load_acs(app)) >= 25 and len(load_bugs(app)) >= 20


def test_app_server_env_clears_inherited_bug_flags():
    from tools.benchmark.app_server import child_env

    env = child_env(["BUG_07"], base={"BUG_01": "1", "BUGS": "all", "BUG_XYZ": "keep", "PATH": "p"})
    assert env == {"BUG_07": "1", "BUG_XYZ": "keep", "PATH": "p"}


def test_app_server_starts_and_stops_real_app(tmp_path):
    import socket
    import urllib.request

    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with AppServer(APPS["buggy_shop"], port, bugs=["BUG_06"], log_path=str(tmp_path / "srv.log")) as srv:
        with urllib.request.urlopen(srv.base_url + "/api/health", timeout=5) as r:
            assert json.loads(r.read())["status"] == "ok"
    with pytest.raises(Exception):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)


def test_rescore_saved_result_applies_new_pricing(tmp_path, monkeypatch):
    from tools.benchmark import run as runner
    from tools.benchmark.apps import APPS

    path = tmp_path / "r.json"
    path.write_text(json.dumps({"meta": {"date": "d"}, "metrics": {}, "run": _record()}), encoding="utf-8")
    monkeypatch.setattr(runner, "_pricing", lambda: {"g-1": {"input_per_mtok": 1, "output_per_mtok": 1}})
    saved = runner.rescore(APPS["buggy_shop"], str(path))
    assert saved["metrics"]["llm"]["cost_usd"] == 2.5
    assert (tmp_path / "r.md").exists()
