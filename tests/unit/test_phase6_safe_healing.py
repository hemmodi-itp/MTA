"""Phase 6 (complete): locator identity, blast radius, audit log, triage signals (known issues, mocked responses,
history, cross-browser), triage refinement (health check / re-runs / cited LLM), healing burn-in, revert on
regression, mode off, triage reuse, model fallback."""
import json
import logging
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from tools.healing import audit, identity
from tools.healing.blast import flow_keys, keys_in, specs_using_keys
from tools.triage import service
from tools.triage.triage import (DATA, ENVIRONMENT, FLAKY, KNOWN_ISSUE, LOCATOR, PRODUCT_DEFECT, UNKNOWN, classify,
                                 load_known_issues, match_known_issue, triage_report)

SAVE = {"tag": "button", "role": "button", "name": "Save product", "label": "", "container": "form|Add product",
        "position": [0, 1], "attrs": {"id": "save-product", "testid": "save-product", "name": "", "type": "submit"}}


# ── identity ────────────────────────────────────────────────────────────────

def test_identical_fingerprint_scores_one_and_renamed_ids_do_not_matter():
    moved = dict(SAVE, attrs={"id": "btn-1", "testid": "submit-x", "name": "", "type": "submit"})
    same = identity.identity_score(SAVE, SAVE)["score"]
    assert same >= 0.95                                # an empty label on both sides is "no signal", not a match
    assert identity.identity_score(SAVE, moved)["score"] == same


def test_different_element_in_same_form_scores_low():
    cancel = dict(SAVE, name="Cancel", position=[1, 2])
    assert identity.identity_score(SAVE, cancel)["score"] < identity.THRESHOLD


def test_reworded_button_in_same_place_still_matches():
    reworded = dict(SAVE, name="Save item")
    assert identity.identity_score(SAVE, reworded)["score"] >= identity.THRESHOLD


def test_choose_refuses_low_scores_and_ambiguity():
    other = {"fingerprint": dict(SAVE, name="Delete", role="link", tag="a"), "entry": {"type": "css", "locator": "a"}}
    assert not identity.choose(SAVE, [other])["accepted"]
    twin_a = {"fingerprint": dict(SAVE, position=[0, 2], attrs={}), "entry": {"type": "css", "locator": "#a"}}
    twin_b = {"fingerprint": dict(SAVE, position=[0, 2], attrs={}), "entry": {"type": "css", "locator": "#b"}}
    r = identity.choose(SAVE, [twin_a, twin_b])
    assert not r["accepted"] and "ambiguous" in r["reason"]
    assert not identity.choose(SAVE, [])["accepted"]


def test_choose_breaks_a_tie_on_a_surviving_attribute():
    keeps_id = {"fingerprint": dict(SAVE), "entry": {"type": "css", "locator": "#save-product"}}
    lost_id = {"fingerprint": dict(SAVE, attrs={}), "entry": {"type": "css", "locator": "#other"}}
    r = identity.choose(SAVE, [lost_id, keeps_id])
    assert r["accepted"] and r["best"]["entry"]["locator"] == "#save-product"


def test_original_fingerprint_sources_in_order():
    dom_el = {"tag_name": "button", "aria_role": "button", "display_text": "Log in",
              "playwright_locators": {"get_by_role": {"role": "button", "name": "Log in"}},
              "semantic_locators": {"label": ""}, "containers": [{"role": "main", "name": None}],
              "attribute_locators": {"testid": "login-button", "id": "login-button"}}
    entry = {"type": "css", "locator": "#x", "description": "Log in button (login-form on /login)"}
    assert identity.original_fingerprint({**entry, "_fingerprint": SAVE})[1] == "recorded"
    fp, src = identity.original_fingerprint(entry, "log_in", dom_el)
    assert src == "dom_scan" and fp["role"] == "button" and fp["name"] == "Log in" and fp["container"] == "main|"
    fp, src = identity.original_fingerprint(entry, "log_in")
    assert src == "entry" and fp["role"] == "button" and fp["name"] == "Log in"


# real browser: the JS fingerprint and the live identity search

HTML_BEFORE = """<main><h1>Add product</h1><form aria-label="Add product">
<label for="name">Name</label><input id="name" data-testid="name" name="name">
<label for="price">Price</label><input id="price" data-testid="price" name="price">
<button id="save" data-testid="save-product" type="submit">Save product</button>
<button type="button">Cancel</button></form></main>"""
# renamed ids/test ids/names and an extra wrapper — the same elements a person would recognise
HTML_AFTER = """<main><h1>Add product</h1><form aria-label="Add product"><div class="row">
<label for="pname">Name</label><input id="pname" data-testid="product-name" name="pname"></div>
<label for="pprice">Price</label><input id="pprice" data-testid="product-price" name="pprice">
<div><button id="submit-btn" data-testid="save-btn" type="submit">Save product</button></div>
<button type="button">Cancel</button></form></main>"""


@pytest.fixture(scope="module")
def browser_page():
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover — environment
        pytest.skip(f"no browser: {exc}")
    page = browser.new_page()
    yield page
    browser.close()
    pw.stop()


def test_live_fingerprint_and_heal_after_renames(browser_page):
    page = browser_page
    page.set_content(HTML_BEFORE)
    fps = {k: identity.live_fingerprint(page, {"type": "testid", "locator": k}) for k in ("name", "price", "save-product")}
    assert fps["save-product"]["role"] == "button" and fps["save-product"]["name"] == "Save product"
    assert fps["name"]["label"] == "Name" and fps["name"]["container"] == "main>form|Add product"
    page.set_content(HTML_AFTER)
    for key, want in (("name", "product-name"), ("price", "product-price"), ("save-product", "save-btn")):
        assert identity.live_fingerprint(page, {"type": "testid", "locator": key}) is None     # broken now
        r = identity.heal_live(page, fps[key])
        assert r["accepted"], r["reason"]
        assert r["entry"] == {"type": "testid", "locator": want}


def test_live_heal_refuses_when_the_element_is_gone(browser_page):
    page = browser_page
    page.set_content(HTML_BEFORE)
    fp = identity.live_fingerprint(page, {"type": "testid", "locator": "save-product"})
    page.set_content(HTML_BEFORE.replace('<button id="save" data-testid="save-product" type="submit">Save product</button>', ""))
    r = identity.heal_live(page, fp)
    assert not r["accepted"]                       # "Cancel" is a button in the form, but not the same element


# ── blast radius ────────────────────────────────────────────────────────────

def test_blast_radius_finds_direct_and_flow_users(tmp_path):
    scripts = tmp_path / "test_scripts"
    (scripts / "M1").mkdir(parents=True)
    (scripts / "M1" / "a.spec.ts").write_text('await action.click("save");')
    (scripts / "M1" / "b.spec.ts").write_text('await flows.login(action, "u", "p");')
    (scripts / "M1" / "c.spec.ts").write_text('await action.dragAndDrop("x", "save");')
    (scripts / "M1" / "d.spec.ts").write_text('await action.click("other");')
    flows = tmp_path / "flows.generated.ts"
    flows.write_text('export async function login(action: ActionEngine, u: string, p: string): Promise<void> {\n'
                     '    await action.enterText("user", u);\n    await action.click("save");\n}\n')
    assert specs_using_keys(str(scripts), ["save"], str(flows)) == ["M1/a.spec.ts", "M1/b.spec.ts", "M1/c.spec.ts"]
    assert keys_in('action.dragAndDrop("a", "b")') == {"a", "b"}
    assert flow_keys(flows.read_text()) == {"login": {"user", "save"}}


# ── audit log ───────────────────────────────────────────────────────────────

def test_audit_append_and_read(tmp_path):
    audit.append(str(tmp_path), {"run_id": "r1", "outcome": "applied", "target": "k"})
    audit.append(str(tmp_path), {"run_id": "r2", "outcome": "proposed", "target": "k"})
    rows = audit.read(str(tmp_path))
    assert [r["approver"] for r in rows] == ["auto", "pending"] and all(r["timestamp"] for r in rows)
    assert [r["run_id"] for r in audit.read(str(tmp_path), "r2")] == ["r2"]
    assert audit.append("", {"outcome": "applied"})["approver"] == "auto"      # no folder: not written, no error


# ── triage signals ──────────────────────────────────────────────────────────

def test_known_issue_wins_and_expired_entries_do_not(tmp_path):
    (tmp_path / "known_issues.yaml").write_text(
        "issues:\n  - {id: KI-1, test: 'checkout total', error: 'Total', ticket: SHOP-1, note: rounding}\n"
        "  - {id: KI-2, spec: 'M9/', expires: 2020-01-01}\n  - {note: 'no matcher - skipped'}\n")
    issues = load_known_issues(str(tmp_path))
    assert [i["id"] for i in issues] == ["KI-1", "KI-2"]
    hit = match_known_issue(issues, "M4/a.spec.ts", "checkout total is rounded", "Expected Total: 10")
    assert hit["id"] == "KI-1"
    assert match_known_issue(issues, "M9/x.spec.ts", "t", "e", today=date(2026, 1, 1)) is None
    r = classify("failed", "Expected Total: 10", [], hit)
    assert r["verdict"] == KNOWN_ISSUE and "SHOP-1" in r["evidence"][0]


@pytest.mark.parametrize("ann,err,verdict", [
    ([{"type": "network_error", "description": "POST http://h/api -> 500"}], "toHaveText", PRODUCT_DEFECT),
    ([{"type": "network_error", "description": "GET http://h/api -> 503 (mocked)"}], "toHaveText", PRODUCT_DEFECT),
    ([{"type": "network_error", "description": "GET http://h/api -> 503"}], "x", ENVIRONMENT),
    # a negative test's expected 400 does not hide a locator failure
    ([{"type": "network_error", "description": "POST http://h/products -> 400"}],
     "[locator_key=save] Timeout 5000ms exceeded. waiting for getByTestId('save')", LOCATOR),
    ([{"type": "network_error", "description": "GET http://h/x -> 404"}], "something odd", PRODUCT_DEFECT),
    ([], "something odd", UNKNOWN),
])
def test_network_annotations_ordering(ann, err, verdict):
    assert classify("failed", err, ann)["verdict"] == verdict


def _pw_report(tests):
    return {"suites": [{"specs": [{"file": f"/p/test_creation/test_scripts/{sf}", "title": t,
                                   "tests": [{"status": st, "projectName": proj,
                                              "results": [{"error": {"message": err}}] if err else [{}]}
                                             for st, proj, err in runs]}
                                  for sf, t, runs in tests]}]}


def test_triage_report_history_and_cross_browser(tmp_path):
    jdir = tmp_path / "json"
    jdir.mkdir()
    row = ("M1/a.spec.ts", "t1")
    for i, st in enumerate(["passed", "failed", "passed"]):
        (jdir / f"2026010{i}_results.json").write_text(json.dumps(_pw_report([(*row, [(st, "chromium", None)])])))
    cur = jdir / "20260109_results.json"
    cur.write_text(json.dumps(_pw_report([(*row, [("unexpected", "webkit", "toHaveText failed"),
                                                   ("expected", "chromium", None)])])))
    out = triage_report(str(cur), str(tmp_path))
    ev = " | ".join(out["tests"][0]["evidence"])
    assert "cross-browser: passes in another browser" in ev and "webkit failed" in ev
    assert "2/3 previous run(s) passed" in ev and "flipped 2x" in ev


# ── triage refinement ───────────────────────────────────────────────────────

def _triage(*items):
    return {"tests": [{"spec_file": sf, "test_name": t, "verdict": v, "evidence": [], "error": err}
                      for sf, t, v, err in items], "counts": {}}


def test_environment_unhealthy_is_reported_not_rerun():
    rerun = MagicMock()
    t = service.refine(_triage(("a", "t", ENVIRONMENT, "ECONNREFUSED")), rerun=rerun,
                       health=lambda: (False, "down"), flaky_rerun=False)
    rerun.assert_not_called()
    assert "health check failed: down" in t["tests"][0]["evidence"]


def test_environment_healthy_rerun_recovers_or_reclassifies():
    t = service.refine(_triage(("a", "t1", ENVIRONMENT, "x"), ("a", "t2", ENVIRONMENT, "x")),
                       rerun=lambda keys, n: {("a", "t1"): {"statuses": ["passed"]},
                                              ("a", "t2"): {"statuses": ["failed"], "error": "strict mode violation: x"}},
                       health=lambda: (True, "ok"), flaky_rerun=False)
    by = {i["test_name"]: i for i in t["tests"]}
    assert by["t1"]["recovered"] and by["t1"]["verdict"] == ENVIRONMENT
    assert by["t2"]["verdict"] == LOCATOR and "re-run failed differently" in by["t2"]["evidence"][0]


def test_flaky_rerun_separates_flaky_from_consistent():
    calls = []

    def rerun(keys, n):
        calls.append(n)
        return {("a", "p"): {"statuses": ["failed", "passed", "failed"]}, ("a", "c"): {"statuses": ["failed"] * 3}}
    t = service.refine(_triage(("a", "p", PRODUCT_DEFECT, "e"), ("a", "c", PRODUCT_DEFECT, "e"),
                               ("a", "k", KNOWN_ISSUE, "e")), rerun=rerun)
    by = {i["test_name"]: i for i in t["tests"]}
    assert calls == [3]
    assert by["p"]["verdict"] == FLAKY and "passed 1/3" in by["p"]["evidence"][0]
    assert by["c"]["verdict"] == PRODUCT_DEFECT and "consistent" in by["c"]["evidence"][-1]
    assert t["counts"] == {FLAKY: 1, PRODUCT_DEFECT: 1, KNOWN_ISSUE: 1}


@pytest.mark.parametrize("answer,verdict,note", [
    ({"verdict": DATA, "quotes": ["E11000 duplicate key"], "reason": "dup"}, DATA, "LLM verdict"),
    ({"verdict": DATA, "quotes": ["made up text"]}, UNKNOWN, "not in the evidence"),
    ({"verdict": "flaky", "quotes": ["E11000 duplicate key"]}, UNKNOWN, "not one of"),
    ({"verdict": DATA, "quotes": []}, UNKNOWN, "no evidence quoted"),
])
def test_llm_for_unknown_must_cite_the_error(answer, verdict, note):
    t = service.refine(_triage(("a", "t", UNKNOWN, "MongoError: E11000 duplicate key on users")),
                       llm=lambda item: answer, flaky_rerun=False)
    assert t["tests"][0]["verdict"] == verdict and note in t["tests"][0]["evidence"][-1]


def test_llm_errors_leave_unknown():
    def boom(item):
        raise TimeoutError("slow")
    t = service.refine(_triage(("a", "t", UNKNOWN, "x")), llm=boom, flaky_rerun=False)
    assert t["tests"][0]["verdict"] == UNKNOWN and "unavailable" in t["tests"][0]["evidence"][-1]


def test_statuses_from_report_and_grep():
    rep = _pw_report([("M1/a.spec.ts", "t (x) @smoke", [("passed", "c", None), ("unexpected", "c", "boom")])])
    out = service.statuses_from_report(rep)
    assert out[("M1/a.spec.ts", "t (x) @smoke")]["statuses"] == ["passed", "unexpected"]
    assert out[("M1/a.spec.ts", "t (x) @smoke")]["error"] == "boom"
    assert service.grep_for_titles(["t (x) @smoke", "t (x) @smoke"]) == r"t\ \(x\)\ @smoke"


# ── healing agent: blast radius revert, burn-in, mode off, triage reuse, model fallback ──

from agents.test_execution.healing.tools import HealingRunContext, _check_blast_radius, _run_tests   # noqa: E402


def _ctx(tmp_path, report=None):
    rep = tmp_path / "r_results.json"
    rep.write_text(json.dumps(report or _pw_report([("M1/b.spec.ts", "other", [("expected", "c", None)])])))
    lm = tmp_path / "locator_map.json"
    lm.write_text(json.dumps({"save": {"type": "css", "locator": "#new"}}))
    return HealingRunContext("p", str(tmp_path / "scripts"), str(tmp_path / "reports"), str(rep), [], {}, "", {}, {},
                             logging.getLogger("t"), locator_map={"save": {"type": "css", "locator": "#new"}},
                             locator_map_path=str(lm), run_id="r")


def test_blast_radius_regression_reverts_the_key(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.remaining = {"M1/a.spec.ts": {"t": "err"}}
    ctx.repaired["save"] = {"before": {"type": "css", "locator": "#old"}, "after": {"type": "css", "locator": "#new"},
                            "spec_file": "M1/a.spec.ts", "test_name": "t", "blast_radius": ["M1/a.spec.ts", "M1/b.spec.ts"]}
    results = [{"spec_file": "/x/test_creation/test_scripts/M1/b.spec.ts", "test_title": "other", "status": "failure"}]
    out = _check_blast_radius(ctx, dict(ctx.repaired), results)
    assert out == [{"key": "save", "broke": ["M1/b.spec.ts :: other"]}]
    assert json.loads(open(ctx.locator_map_path).read())["save"]["locator"] == "#old"
    assert "save" not in ctx.repaired and ctx.not_healable[0]["test_name"] == "t"
    assert audit.read(ctx.reports_dir)[-1]["outcome"] == "reverted"


def test_run_tests_adds_the_blast_radius(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.remaining = {"M1/a.spec.ts": {"t": "err"}}
    ctx.repaired["save"] = {"before": {}, "after": {}, "spec_file": "M1/a.spec.ts", "test_name": "t",
                            "blast_radius": ["M1/a.spec.ts", "M1/b.spec.ts"]}
    agent = MagicMock()
    agent.execute.return_value = {"status": "success", "passed": 2, "failed": 0, "results": [
        {"spec_file": "/x/test_creation/test_scripts/M1/a.spec.ts", "test_title": "t", "status": "success"},
        {"spec_file": "/x/test_creation/test_scripts/M1/b.spec.ts", "test_title": "other", "status": "success"}]}
    with patch("agents.test_execution.ui_execution.agent.UIExecutionAgent", return_value=agent):
        r = _run_tests(ctx, ["M1/a.spec.ts"])
    assert agent.execute.call_args[0][0]["spec_files"] == ["M1/a.spec.ts", "M1/b.spec.ts"]
    assert r["all_resolved"] and ctx.repaired["save"]["verified"] and ctx.fixed == {("M1/a.spec.ts", "t")}


def _healing_project(tmp_path, monkeypatch, healing_yaml):
    import agents.test_execution.healing.agent as hagent
    monkeypatch.setattr(hagent, "_ASSETS_BASE", str(tmp_path))
    pdir = tmp_path / "proj"
    (pdir / "test_execution" / "reports" / "json").mkdir(parents=True)
    (pdir / "project.yaml").write_text(healing_yaml)
    rep = pdir / "test_execution" / "reports" / "json" / "20260101_results.json"
    rep.write_text(json.dumps(_pw_report([("M1/a.spec.ts", "t", [("unexpected", "c", "strict mode violation: x")])])))
    return hagent, pdir, rep


def test_mode_off_is_triage_only(tmp_path, monkeypatch):
    hagent, pdir, rep = _healing_project(tmp_path, monkeypatch, "healing: {mode: off}\n")
    import agents.test_execution.triage.agent as tagent
    monkeypatch.setattr(tagent, "_ASSETS_BASE", str(tmp_path))
    with patch.object(hagent.HealingAgent, "_run_adk_healing") as loop:
        out = hagent.HealingAgent().execute({"project_name": "proj", "triage_reruns": False}, {})
    loop.assert_not_called()
    assert out["mode"] == "off" and out["triage"]["counts"] == {LOCATOR: 1}
    assert (pdir / "test_execution" / "reports" / "triage.json").exists()


def test_fresh_triage_json_is_reused(tmp_path, monkeypatch):
    hagent, pdir, rep = _healing_project(tmp_path, monkeypatch, "healing: {mode: off}\n")
    (pdir / "test_execution" / "reports" / "triage.json").write_text(json.dumps(
        {"report": rep.name, "counts": {PRODUCT_DEFECT: 1}, "tests": [
            {"spec_file": "M1/a.spec.ts", "test_name": "t", "verdict": PRODUCT_DEFECT, "evidence": ["e"]}]}))
    with patch("agents.test_execution.triage.agent.run_triage") as rt:
        out = hagent.HealingAgent().execute({"project_name": "proj"}, {})
    rt.assert_not_called()
    assert out["triage"]["counts"] == {PRODUCT_DEFECT: 1}


def test_model_fallback_uses_the_next_model(tmp_path, monkeypatch):
    hagent, pdir, rep = _healing_project(tmp_path, monkeypatch, "")       # no healing section: legacy, no triage
    calls = []

    def loop(self, ctx, model, n):
        calls.append(model)
        if model == "m1":
            raise ConnectionError("model m1 down")
    with patch.object(hagent, "resolve_adk_model_chain", return_value=[("gemini", "m1"), ("external", "m2")]), \
            patch.object(hagent.HealingAgent, "_run_adk_healing", loop):
        out = hagent.HealingAgent().execute({"project_name": "proj"}, {})
    assert calls == ["m1", "m2"] and out["model"] == "external"


def test_burn_in_marks_stable_and_unstable(tmp_path):
    from agents.test_execution.healing.agent import HealingAgent
    ctx = _ctx(tmp_path)
    ctx.fixed = {("M1/a.spec.ts", "t1"), ("M1/b.spec.ts", "t2")}
    fake = lambda tests, n: {("M1/a.spec.ts", "t1"): {"statuses": ["passed"] * 3},   # noqa: E731
                             ("M1/b.spec.ts", "t2"): {"statuses": ["passed", "failed", "passed"]}}
    with patch("tools.triage.service.make_rerun", return_value=fake):
        out = HealingAgent()._burn_in(ctx)
    assert out == {"stable": ["M1/a.spec.ts"], "unstable": ["M1/b.spec.ts"]}
    assert sorted(r["outcome"] for r in audit.read(ctx.reports_dir)) == ["burn_in_failed", "verified"]


def test_model_chain_records_unresolvable_modes():
    from connectors.adk_model import resolve_adk_model_chain
    chain = resolve_adk_model_chain({"connectors": {"llm": "internal"}, "adk": {"fallback": ["gemini"],
                                                                              "models": {"gemini": "g-1"}}})
    assert chain[0][0] == "internal" and isinstance(chain[0][1], Exception)
    assert chain[1] == ("gemini", "g-1")


def test_triage_agent_writes_triage_and_defects(tmp_path, monkeypatch):
    import agents.test_execution.triage.agent as tagent
    monkeypatch.setattr(tagent, "_ASSETS_BASE", str(tmp_path))
    rdir = tmp_path / "proj" / "test_execution" / "reports" / "json"
    rdir.mkdir(parents=True)
    (rdir / "20260101_results.json").write_text(json.dumps(_pw_report([
        ("M1/a.spec.ts", "t", [("unexpected", "c", "expect(received).toHaveText(expected)")])])))
    out = tagent.TriageAgent().execute({"project_name": "proj", "triage_reruns": False}, {})
    assert out["status"] == "success" and out["counts"] == {PRODUCT_DEFECT: 1}
    assert json.load(open(out["defects"]))[0]["test_name"] == "t"
    assert tagent.TriageAgent().execute({"project_name": "nope"}, {})["status"] == "skipped"


# ── missing element: product or locator? (failure-time identity probe) ─────

ASSERT_MISSING = ("[locator_key=flash] Error: expect(locator).toContainText(expected) failed\n"
                  "Expected substring: \"Product created\"\nError: element(s) not found\n"
                  "  - waiting for getByTestId('flash')")
ACTION_MISSING = "[locator_key=save] Timeout 30000ms exceeded. waiting for getByTestId('save')"


@pytest.mark.parametrize("err,probe,verdict", [
    (ACTION_MISSING, "save: an element with the same identity is on the page — the locator drifted", LOCATOR),
    (ACTION_MISSING, "save: no element with this identity on the page", PRODUCT_DEFECT),
    (ACTION_MISSING, "save: no recorded identity", LOCATOR),
    (ASSERT_MISSING, "flash: no recorded identity", PRODUCT_DEFECT),
    (ASSERT_MISSING, "flash: an element with the same identity is on the page — the locator drifted", LOCATOR),
    ("strict mode violation: getByRole('button') resolved to 2 elements",
     "x: no element with this identity on the page", LOCATOR),
])
def test_missing_element_is_classified_by_the_identity_probe(err, probe, verdict):
    r = classify("failed", err, [{"type": "locator_probe", "description": probe}])
    assert r["verdict"] == verdict, r


def test_ansi_coloured_playwright_errors_are_classified_on_their_text():
    coloured = ("Error: [locator_key=error_message] \x1b[2mexpect(\x1b[22m\x1b[31mlocator\x1b[39m\x1b[2m).\x1b[22m"
                "toContainText\x1b[2m(\x1b[22m\x1b[32mexpected\x1b[39m\x1b[2m)\x1b[22m failed\n\nError: element(s) not "
                "found\n  - waiting for getByTestId('error-message')")
    assert classify("failed", coloured, [])["verdict"] == PRODUCT_DEFECT


def test_dynamic_keys_are_never_live_checked_or_repaired(tmp_path):
    from agents.test_execution.healing.tools import _propose_locator_fix
    scripts = tmp_path / "scripts" / "M1"
    scripts.mkdir(parents=True)
    (scripts / "a.spec.ts").write_text('test("t", async ({ action }) => {\n  await action.verifyText("flash", "ok");\n});\n')
    ctx = _ctx(tmp_path)
    ctx.scripts_dir = str(tmp_path / "scripts")
    ctx.generation_modes = {"M1/a.spec.ts": "action_library"}
    ctx.locator_map = {"flash": {"type": "testid", "locator": "flash", "_dynamic": True}}
    with patch("agents.test_execution.healing.tools._get_validation_page") as page:
        r = _propose_locator_fix(ctx, "M1/a.spec.ts", "t")
    page.assert_not_called()
    assert not r["resolved"] and "already resolves" in r["reason"]
