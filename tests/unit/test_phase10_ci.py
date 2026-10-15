"""Phase 10: quarantine, health check, burn-in admission, order independence, selective execution, CI exit codes."""

import json
import os
from datetime import date

from tools.ci.run import exit_code
from tools.execution import admission, health, quarantine as qz, selective

SPEC = "M01/test_a.spec.ts"
FULL = "application_assets/projects/p/test_creation/test_scripts/" + SPEC


def _res(title, status, spec=FULL, err=""):
    return {"spec_file": spec, "test_title": title, "status": status, "errors": [err] if err else []}


# ── quarantine ───────────────────────────────────────────────────────

def test_quarantine_round_trip_release_and_reset(tmp_path):
    d = str(tmp_path)
    q = qz.load(d)
    key = qz.test_key(FULL, "save works")
    assert key == f"{SPEC} :: save works"
    assert qz.add(q, key, "manual", "Timeout 5000ms exceeded", owner="qa", today=date(2026, 10, 1))
    assert not qz.add(q, key, "manual")
    q["release_after"] = 2
    qz.save(d, q)
    assert qz.load(d)["tests"][0]["failure_signature"] == "Timeout Nms exceeded"

    out = qz.record_run(d, [_res("save works", "passed")])
    assert out["released"] == [] and qz.load(d)["tests"][0]["stable_runs"] == 1
    out = qz.record_run(d, [_res("save works", "failed")])
    assert out["reset"] == [key] and qz.load(d)["tests"][0]["stable_runs"] == 0
    qz.record_run(d, [_res("save works", "passed")])
    out = qz.record_run(d, [_res("save works", "passed")], today=date(2026, 10, 9))
    assert out["released"] == [key]
    q = qz.load(d)
    assert q["tests"] == [] and q["released"][0]["released"] == "2026-10-09"


def test_quarantine_auto_adds_repeat_flaky_and_split(tmp_path):
    d = str(tmp_path)
    key = qz.test_key(FULL, "t1")
    out = qz.record_run(d, [_res("t1", "flaky", err="boom")], flaky_history={})
    assert out["added"] == []                                    # first flaky: not yet
    out = qz.record_run(d, [_res("t1", "flaky", err="boom")], flaky_history={key: 1})
    assert out["added"] == [key] and qz.load(d)["tests"][0]["reason"] == "flaky"
    gating, quarantined = qz.split_results([_res("t1", "failed"), _res("t2", "failed")], qz.load(d))
    assert [r["test_title"] for r in gating] == ["t2"] and [r["test_title"] for r in quarantined] == ["t1"]


def test_flaky_counts_reads_reports(tmp_path):
    rep = {"suites": [{"specs": [{"file": FULL, "title": "t1", "tests": [{"status": "flaky"}]}]}]}
    for i in range(3):
        (tmp_path / f"2026100{i}_results.json").write_text(json.dumps(rep), encoding="utf-8")
    assert qz.flaky_counts(str(tmp_path)) == {f"{SPEC} :: t1": 3}


# ── health check ─────────────────────────────────────────────────────

def _project_yaml(tmp_path, extra=""):
    (tmp_path / "project.yaml").write_text(
        "auth:\n  roles:\n    user: {username: u}\n    guest: {anonymous: true}\n"
        "execution:\n  role_auth: true\n"
        "health_check:\n  auth_url: /account\n  seed:\n    - {path: /api/products, status: 200, contains: Widget}\n" + extra,
        encoding="utf-8")
    (tmp_path / ".auth").mkdir()
    (tmp_path / ".auth" / "user.json").write_text(json.dumps({"cookies": [{"name": "s", "value": "1"}]}), encoding="utf-8")


def test_health_unreachable_blocks(tmp_path):
    _project_yaml(tmp_path)
    res = health.check(str(tmp_path), "http://app", fetch=lambda url, c, t: (0, "", "ConnectionRefusedError"))
    assert res["ok"] is False and [c["name"] for c in res["checks"]] == ["base_url"]


def test_health_expired_session_refreshed(tmp_path):
    _project_yaml(tmp_path)
    state = {"fresh": False}

    def fetch(url, cookies, timeout):
        if url.endswith("/account"):
            return (200, "", "ok") if state["fresh"] else (302, "/login?next=/account", "")
        if url.endswith("/api/products"):
            return 200, "", '[{"name": "Widget"}]'
        return 200, "", "home"
    refreshed = []
    res = health.check(str(tmp_path), "http://app", refresh=lambda role: (refreshed.append(role), state.update(fresh=True)),
                       fetch=fetch)
    assert res["ok"] and refreshed == ["user"]
    assert {c["name"] for c in res["checks"]} == {"base_url", "auth:user", "seed:/api/products"}


def test_health_missing_seed_data_blocks(tmp_path):
    _project_yaml(tmp_path)
    res = health.check(str(tmp_path), "http://app",
                       fetch=lambda url, c, t: (200, "", "[]") if "api" in url else (200, "", "ok"))
    assert not res["ok"]
    bad = [c for c in res["checks"] if not c["ok"]]
    assert bad[0]["name"] == "seed:/api/products" and "missing 'Widget'" in bad[0]["detail"]


def test_health_base_only_skips_auth_and_seed(tmp_path):
    _project_yaml(tmp_path)
    seen = []
    res = health.check(str(tmp_path), "http://app", base_only=True,
                       fetch=lambda url, c, t: (seen.append(url), (200, "", "ok"))[1])
    assert res["ok"] and seen == ["http://app"] and [c["name"] for c in res["checks"]] == ["base_url"]
    down = health.check(str(tmp_path), "http://app", base_only=True, fetch=lambda *a: (0, "", "refused"))
    assert down["ok"] is False


def test_health_without_block_is_skipped(tmp_path):
    (tmp_path / "project.yaml").write_text("execution: {}\n", encoding="utf-8")
    assert health.check(str(tmp_path), "http://app", fetch=lambda *a: (0, "", ""))["ok"] is True


# ── admission / order independence ───────────────────────────────────

def _report(tmp_path, name, per_test):
    """per_test: {title: [statuses]} -> a Playwright JSON report file."""
    rep = {"suites": [{"title": "s", "suites": [{"specs": [
        {"file": FULL, "title": t, "tests": [{"status": s} for s in sts]} for t, sts in per_test.items()]}]}]}
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(rep), encoding="utf-8")
    return str(p)


def _suite(tmp_path, specs):
    from contracts.artifacts import save_artifact
    (tmp_path / "test_creation").mkdir(exist_ok=True)
    save_artifact("test_suite", str(tmp_path / "test_creation" / "test_suite.json"), {"specs": specs})


def test_admission_burn_in(tmp_path):
    _suite(tmp_path, [{"spec_id": "A", "file": SPEC, "status": "new"},
                      {"spec_id": "B", "file": "M02/old.spec.ts", "status": "passed"}])
    calls = []

    def runner(req):
        calls.append(req)
        return {"status": "success", "report_json": _report(tmp_path, "burn", {
            "stable": ["expected"] * 5, "wobbly": ["expected", "unexpected", "expected", "expected", "expected"],
            "broken": ["unexpected"] * 5}), "results": [_res("wobbly", "failed", err="Timeout 30000ms")]}
    out = admission.admit(str(tmp_path), "p", runner=runner)
    assert calls == [{"spec_files": [SPEC], "repeat_each": 5}]
    assert out["admitted"] == [f"{SPEC} :: stable"]
    assert out["quarantined"] == [f"{SPEC} :: wobbly"] and out["failing"] == [f"{SPEC} :: broken"]
    q = qz.load(str(tmp_path))
    assert q["tests"][0]["reason"] == "burn_in_failed" and q["tests"][0]["failure_signature"] == "Timeout Nms"
    from contracts.artifacts import load_payload
    spec = load_payload("test_suite", str(tmp_path / "test_creation" / "test_suite.json"))["specs"][0]
    assert spec["status"] == "new"                               # not every test admitted
    assert spec["admission"]["admitted"] == 1 and spec["admission"]["failing"] == 1


def test_admission_all_stable_admits_spec_and_caps(tmp_path):
    _suite(tmp_path, [{"spec_id": "A", "file": SPEC, "status": "healed"},
                      {"spec_id": "B", "file": "M02/b.spec.ts", "status": "new"}])
    out = admission.admit(str(tmp_path), "p", max_specs=1,
                          runner=lambda req: {"report_json": _report(tmp_path, "ok", {"t": ["expected"] * 5})})
    assert out["deferred"] == 1 and out["admitted"] == [f"{SPEC} :: t"]
    from contracts.artifacts import load_payload
    specs = load_payload("test_suite", str(tmp_path / "test_creation" / "test_suite.json"))["specs"]
    assert specs[0]["status"] == "admitted" and specs[1]["status"] == "new"


def test_admission_nothing_new(tmp_path):
    _suite(tmp_path, [{"spec_id": "A", "file": SPEC, "status": "admitted"}])
    assert admission.admit(str(tmp_path), "p", runner=lambda r: 1 / 0)["specs"] == 0


def test_order_check_flags_mode_dependent_tests(tmp_path):
    def runner(req):
        if req.get("workers") == 1:                              # isolated: t2 loses state set up by another file
            return {"report_json": _report(tmp_path, "iso", {"t1": ["expected"], "t2": ["unexpected"]})}
        return {"report_json": _report(tmp_path, f"w{req.get('workers')}", {"t1": ["expected"], "t2": ["expected"]})}
    out = admission.order_check(str(tmp_path), "p", [SPEC], runner=runner)
    assert out["tests"] == 2 and [d["test"] for d in out["order_dependent"]] == [f"{SPEC} :: t2"]
    assert out["order_dependent"][0]["modes"] == {"normal": "pass", "isolated_reverse": "fail", "workers4": "pass"}
    assert qz.load(str(tmp_path))["tests"][0]["reason"] == "order_dependent"


# ── selective execution ──────────────────────────────────────────────

def _selective_project(tmp_path):
    comp, scripts = tmp_path / "test_comprehension", tmp_path / "test_creation" / "test_scripts"
    (scripts / "M01").mkdir(parents=True)
    (scripts / "api").mkdir()
    comp.mkdir()
    (comp / "requirements.json").write_text(json.dumps({"requirements": [{"id": "R1", "acceptance_criteria": [
        {"id": "AC-1", "statement": "cart total"}, {"id": "AC-2", "statement": "login"}]}]}), encoding="utf-8")
    (comp / "app_map.json").write_text(json.dumps({"states": [{"url_template": "/cart", "structural_hash": "h1"}]}),
                                       encoding="utf-8")
    (scripts / "M01" / "a.spec.ts").write_text('test("A one", async () => {});\n', encoding="utf-8")
    (scripts / "api" / "api_cart.spec.ts").write_text('  test("POST /cart — valid", async () => {});\n', encoding="utf-8")
    (comp / "api_inventory.json").write_text(json.dumps({"endpoints": [
        {"method": "POST", "path_template": "/cart", "request": {"fields": ["qty"]}}]}), encoding="utf-8")
    (tmp_path / "test_creation" / "test_plans.json").write_text(json.dumps({"plans": {"M01": {"tests": [
        {"title": "AC2 test", "ac_ids": ["AC-2"]}, {"title": "critical", "priority": "P0"},
        {"title": "cart page", "case_id": "TC1"}]}}}), encoding="utf-8")
    (tmp_path / "test_creation" / "test_cases.json").write_text(json.dumps({"test_cases": [
        {"id": "TC1", "target": {"url_template": "/cart"}}]}), encoding="utf-8")


def test_selective_no_fingerprint_runs_everything(tmp_path):
    _selective_project(tmp_path)
    sel = selective.select(tmp_path)
    assert sel["full"] is True and sel["grep"] is None


def test_selective_picks_impacted(tmp_path):
    _selective_project(tmp_path)
    prev = selective.fingerprint(tmp_path)
    assert selective.select(tmp_path, previous=prev)["tests"] == ["critical"]      # nothing changed: P0 only
    comp = tmp_path / "test_comprehension"
    reqs = json.loads((comp / "requirements.json").read_text())
    reqs["requirements"][0]["acceptance_criteria"][1]["statement"] = "login with SSO"
    (comp / "requirements.json").write_text(json.dumps(reqs), encoding="utf-8")
    (comp / "app_map.json").write_text(json.dumps({"states": [{"url_template": "/cart", "structural_hash": "h2"}]}),
                                       encoding="utf-8")
    (comp / "api_inventory.json").write_text(json.dumps({"endpoints": [
        {"method": "POST", "path_template": "/cart", "request": {"fields": ["qty", "coupon"]}}]}), encoding="utf-8")
    sel = selective.select(tmp_path, previous=prev)
    assert sel["full"] is False
    assert sel["reasons"] == {"AC2 test": "AC changed: AC-2", "critical": "P0 — always runs",
                              "cart page": "page changed: /cart", "POST /cart — valid": "endpoint changed: POST /cart"}
    assert "A one" not in sel["tests"] and "AC2\\ test" in sel["grep"]


def test_selective_spec_change(tmp_path):
    _selective_project(tmp_path)
    prev = selective.fingerprint(tmp_path)
    (tmp_path / "test_creation" / "test_scripts" / "M01" / "a.spec.ts").write_text(
        'test("A one", async () => { /* edited */ });\n', encoding="utf-8")
    assert selective.select(tmp_path, previous=prev)["reasons"]["A one"] == "spec changed: M01/a.spec.ts"


# ── CI exit codes ────────────────────────────────────────────────────

def test_ci_exit_codes():
    q = {"tests": [{"test": f"{SPEC} :: wobbly"}]}
    assert exit_code({"status": "environment_blocked"}, {}, q) == 3
    assert exit_code({"status": "failed"}, {}, q) == 1
    assert exit_code({"status": "success"}, {"verdict": "FAIL"}, q) == 1
    assert exit_code({"status": "success", "results": [_res("x", "failed")]}, {"verdict": "PASS"}, q) == 0
    assert exit_code({"status": "success", "results": [_res("wobbly", "failed")]}, {}, q) == 0   # quarantined
    assert exit_code({"status": "success", "results": [_res("x", "failed")]}, {}, q) == 1
    assert exit_code({"status": "skipped"}, {}, q) == 0


# ── reporting: quarantine without enhanced reporting ─────────────────

def test_reporting_lists_and_updates_quarantine_without_enhanced_reporting(tmp_path, monkeypatch):
    import agents.test_execution.reporting.agent as ra
    from tools.catalog import catalog_manager
    monkeypatch.setattr(ra, "_ASSETS_BASE", str(tmp_path))
    monkeypatch.setattr(catalog_manager, "_ASSETS_BASE", str(tmp_path))
    pdir = tmp_path / "p"
    (pdir / "test_creation").mkdir(parents=True)          # no project.yaml: no reporting.enhanced, no quality_gates
    q = qz.load(str(pdir))
    qz.add(q, qz.test_key(FULL, "canary"), "manual", "boom")
    qz.save(str(pdir), q)
    state = {"run_id": "r1", "outputs": {"ui_execution": {"status": "success", "passed": 1, "failed": 1, "results": [
        _res("canary", "failed", err="boom"), _res("ok", "passed")]}}}
    ra.ReportingAgent().execute({"project_name": "p"}, state)
    rep = json.loads(next((pdir / "test_execution" / "reports" / "json").glob("*_p.json")).read_text(encoding="utf-8"))
    assert rep["quarantine"]["results"] == [{"test": f"{SPEC} :: canary", "status": "failed"}]
    html = next((pdir / "test_execution" / "reports" / "html").glob("*_p.html")).read_text(encoding="utf-8")
    assert 'id="quarantine"' in html and f"{SPEC} :: canary" in html
    state["outputs"]["ui_execution"]["results"] = [_res("canary", "passed")]
    ra.ReportingAgent().execute({"project_name": "p"}, state)
    assert qz.load(str(pdir))["tests"][0]["stable_runs"] == 1        # record_run ran

    other = tmp_path / "o"
    (other / "test_creation").mkdir(parents=True)
    ra.ReportingAgent().execute({"project_name": "o"}, {"run_id": "r2", "outputs": {"ui_execution": {
        "status": "success", "passed": 1, "failed": 0, "results": [_res("ok", "passed")]}}})
    assert not (other / qz.FILE).exists()                              # no quarantine file conjured up
