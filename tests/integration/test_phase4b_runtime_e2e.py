"""
Phase 4 (session 2) acceptance, end to end on the buggy_shop benchmark app (real Chromium, real Playwright 1.64,
through UIExecutionAgent — no mocks):

  * AC2 — two parallel workers (execution.data_isolation -> fullyParallel) run the same create flow with the
          testData + cleanup fixtures: no collision; a literal-data control shows the collision is real.
  * AC3 — a deliberately flaky test is "flaky" (never "passed") in the Playwright JSON, the MTA results, the
          UIExecution result, test_suite.json, traceability.json and the ReportingAgent JSON + HTML report.
  * AC7 — consoleGuard (execution.console_guard: fail) fails a test on a new console error, not on a baseline one.

Run:  python -m pytest tests/integration/test_phase4b_runtime_e2e.py -v -s
Skipped when node_modules/playwright or the buggy_shop app cannot start.
"""

import json
import os
import shutil
import socket
import urllib.request

import pytest

from tools.constants import PROJECTS_BASE

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPECS = os.path.join(ROOT, "tests", "e2e", "phase4b")
PROJECT = "bench_p4b_e2e"          # bench_* is gitignored
FORBIDDEN = "Failed to load resource: the server responded with a status of 403 (Forbidden)"
FLAKY_TITLE = "deliberately flaky: fails first, passes on retry"

pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(ROOT, "node_modules", "playwright", "lib", "program.js")),
    reason="npm install has not been run")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _yaml(base_url: str) -> str:
    return f"""project:
  name: {PROJECT}
  url: {base_url}
environment: local
safety:
  allowed_hosts: [127.0.0.1]
  allow_destructive: true
requirements:
  enabled: true
auth:
  enabled: false
  roles:
    user:
      strategy: setup
      steps:
        - goto: {base_url}/login
        - fill: {{selector: '#username', value: alice}}
        - fill: {{selector: '#password', value: alice-pass-1}}
        - click: '#login-button'
execution:
  role_auth: true
  role_auth_max_age_minutes: 0
  data_isolation: true
  console_guard: fail
  network: on-failure
"""


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


@pytest.fixture(scope="module")
def shop():
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS

    port = _free_port()
    try:
        server = AppServer(APPS["buggy_shop"], port=port).start()
    except Exception as exc:  # pragma: no cover — environment
        pytest.skip(f"buggy_shop did not start: {exc}")
    pdir = os.path.join(PROJECTS_BASE, PROJECT)
    shutil.rmtree(pdir, ignore_errors=True)
    scripts = os.path.join(pdir, "test_creation", "test_scripts", "P4B")
    os.makedirs(scripts)
    for f in os.listdir(SPECS):
        shutil.copy(os.path.join(SPECS, f), scripts)
    with open(os.path.join(pdir, "project.yaml"), "w", encoding="utf-8") as fh:
        fh.write(_yaml(server.base_url))
    # Phase 2 baseline: the user role's 403 console error on /admin is known
    _write(os.path.join(pdir, "test_comprehension", "baseline.json"), {
        "schema_version": 2, "artifact": "baseline", "project": PROJECT, "states": {
            "S-admin": {"url": f"{server.base_url}/admin", "role": "user", "console_errors": [{"text": FORBIDDEN}],
                        "console_warnings": [], "page_errors": [], "failed_requests": []},
            "S-products": {"url": f"{server.base_url}/products", "role": "user", "console_errors": [],
                           "console_warnings": [], "page_errors": [], "failed_requests": []}}})
    files = {sid: f"P4B/{f}" for f in os.listdir(SPECS) for sid in [f[5:14]]}
    _write(os.path.join(pdir, "test_creation", "test_suite.json"), {
        "schema_version": 2, "artifact": "test_suite", "project": PROJECT,
        "specs": [{"spec_id": sid, "file": rel, "module_id": "P4B", "status": "new", "last_result": None}
                  for sid, rel in sorted(files.items())]})
    _write(os.path.join(pdir, "test_creation", "traceability.json"), {
        "schema_version": 2, "artifact": "traceability", "project": PROJECT,
        "acs": {"AC-90.1": {"statement": "flaky demo", "tc_ids": ["P4B_TC_001"], "status": "covered"},
                "AC-90.2": {"statement": "stable demo", "tc_ids": ["P4B_TC_002"], "status": "covered"}},
        "tests": {"P4B_TC_001": {"scenario_id": "P4_BS_001", "spec_file": files["P4_BS_001"], "test_title": FLAKY_TITLE,
                                 "ac_ids": ["AC-90.1"]},
                  "P4B_TC_002": {"scenario_id": "P4_BS_001", "spec_file": files["P4_BS_001"], "test_title": "stable check",
                                 "ac_ids": ["AC-90.2"]}}})
    yield server, pdir
    server.stop()
    if not os.environ.get("MTA_KEEP_E2E"):
        shutil.rmtree(pdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _real_projects_base(_isolate_projects_base, monkeypatch):
    """tests/conftest.py points every PROJECTS_BASE alias at a temp folder; the real Playwright runner reads the
    project from application_assets/projects/ under the repo root, so the aliases this run touches go back."""
    import tools.constants as constants
    import agents.test_execution.ui_execution.agent as ui
    import agents.test_execution.reporting.agent as rep
    import tools.catalog.catalog_manager as cat
    monkeypatch.setattr(constants, "PROJECTS_BASE", PROJECTS_BASE)
    monkeypatch.setattr(ui, "_ASSETS_BASE", PROJECTS_BASE)
    for mod in (rep, cat):
        if hasattr(mod, "_ASSETS_BASE"):
            monkeypatch.setattr(mod, "_ASSETS_BASE", PROJECTS_BASE)
    monkeypatch.chdir(ROOT)


def _api_get_as_user(base_url, path):
    """GET an authenticated buggy_shop API path as alice (the sid cookie from a form login)."""
    import http.cookiejar
    import urllib.parse
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.open(f"{base_url}/login", urllib.parse.urlencode({"username": "alice", "password": "alice-pass-1"}).encode())
    with opener.open(f"{base_url}{path}") as resp:
        return json.loads(resp.read().decode())


def _execute(**request):
    from agents.test_execution.ui_execution.agent import UIExecutionAgent

    return UIExecutionAgent().execute({"project_name": PROJECT, "headless": True, **request}, {})


def _mta(out):
    return {t["title"]: t for t in json.load(open(out["mta_results"], encoding="utf-8"))["tests"]}


def test_ac2_two_parallel_workers_same_create_flow_no_collision(shop):
    server, _ = shop
    out = _execute(grep="@isolation|@control")
    statuses = {r["test_title"]: r["status"] for r in out["results"]}
    print(json.dumps(statuses, indent=2))
    assert all(statuses[f"isolated create {i}"] == "success" for i in range(1, 7)), statuses
    assert statuses["control: the same literal data collides"] == "success"   # the collision is real

    created = [json.loads(a["description"]) for t in _mta(out).values()
               for a in t["annotations"] if a["type"] == "created"]
    print(json.dumps(created, indent=2))
    assert len(created) == 6
    assert len({c["id"] for c in created}) == 6, "two tests landed on the same product"
    assert len({c["name"] for c in created}) == 6
    run_part = {c["prefix"][:7] for c in created}
    assert len(run_part) == 1 and all(c["name"].startswith(c["prefix"]) for c in created)
    workers = {c["worker"] for c in created}
    assert len(workers) >= 2, f"fullyParallel did not spread the file over 2 workers: {workers}"
    overlap = any(a["worker"] != b["worker"] and a["started"] < b["ended"] and b["started"] < a["ended"]
                  for a in created for b in created)
    assert overlap, "no two create flows ran at the same time"
    # cleanup removed every created product (deleted in reverse order through the api fixture)
    remaining = _api_get_as_user(server.base_url, f"/api/products?q={created[0]['prefix'][:7]}")
    items = remaining.get("items", remaining) if isinstance(remaining, dict) else remaining
    assert not [p for p in items if str(p.get("name", "")).startswith("mta")], items
    assert all(not t["cleanup_failures"] for t in _mta(out).values())


def test_ac3_flaky_test_is_flaky_end_to_end(shop):
    _, pdir = shop
    out = _execute(grep="@flaky-demo")
    # 1. Playwright JSON
    pw = json.load(open(out["report_json"], encoding="utf-8"))
    pw_status = {s["title"]: t["status"] for suite in pw["suites"] for sub in [suite, *suite.get("suites", [])]
                 for s in sub.get("specs", []) for t in s["tests"]}
    assert pw_status[FLAKY_TITLE] == "flaky"
    # 2. MTA results
    mta = _mta(out)[FLAKY_TITLE]
    assert mta["status"] == "flaky" and mta["retries"] == 1 and [a["status"] for a in mta["attempts"]] == ["failed", "passed"]
    # 3. UIExecution result
    by = {r["test_title"]: r for r in out["results"]}
    assert by[FLAKY_TITLE]["status"] == "flaky" and out["flaky"] == 1
    assert out["passed"] == 1 and by["stable check"]["status"] == "success"
    assert out["results_source"] == "mta_results" and out["retries"] == 1
    # 4. traceability.json
    trace = json.load(open(os.path.join(pdir, "test_creation", "traceability.json"), encoding="utf-8"))
    trace = trace.get("payload", trace)
    assert trace["tests"]["P4B_TC_001"]["latest_result"]["status"] == "flaky"
    assert trace["tests"]["P4B_TC_002"]["latest_result"]["status"] == "passed"
    assert trace["acs"]["AC-90.1"]["result"] == "flaky" and trace["summary"]["acs_flaky"] == 1
    # 5. ReportingAgent: test_suite.json + JSON / HTML report
    from agents.test_execution.reporting.agent import ReportingAgent
    rep = ReportingAgent().execute({"project_name": PROJECT}, {
        "run_id": "p4b", "workflow_name": "e2e", "execution_trace": [{"step": "ui_execution", "status": "success"}],
        "errors": [], "outputs": {"ui_execution": out}})
    suite = json.load(open(os.path.join(pdir, "test_creation", "test_suite.json"), encoding="utf-8"))
    suite = suite.get("payload", suite)
    assert {s["spec_id"]: s["last_result"] for s in suite["specs"]}["P4_BS_001"] == "flaky"
    paths = {k: v for k, v in rep.items() if isinstance(v, str) and v.endswith((".json", ".html"))}
    report_json = json.load(open(next(p for p in paths.values() if p.endswith(".json")), encoding="utf-8"))
    ter = report_json["test_execution_report"]
    assert ter["flaky"] == 1 and ter["passed"] == 1
    assert {r["test_case_name"]: r["status"] for r in ter["results"]}[FLAKY_TITLE] == "flaky"
    html = open(next(p for p in paths.values() if p.endswith(".html")), encoding="utf-8").read()
    assert ">FLAKY<" in html and "⚠ Flaky" in html


def test_ac7_console_guard_new_error_fails_baseline_error_does_not(shop):
    out = _execute(grep="@console")
    by = {r["test_title"]: r for r in out["results"]}
    print(json.dumps({k: (v["status"], v["errors"][:1]) for k, v in by.items()}, indent=2))
    assert by["baseline console error does not fail"]["status"] == "success"
    new = by["new console error fails the test"]
    assert new["status"] == "failed"
    assert any("consoleGuard: 1 new console error(s) not in baseline.json" in e and "/products/999999" in e
               for e in new["errors"])
    mta = _mta(out)["new console error fails the test"]
    assert any(a["type"] == "console_new_error" for a in mta["annotations"])
    # redacted network evidence on the failing test; no credential anywhere in the reports
    har = next(a for a in mta["attachments"] if a["name"] == "network.har")
    har_text = open(har["path"], encoding="utf-8").read()
    assert json.loads(har_text)["log"]["version"] == "1.2"
    # the role's session cookie (from .auth/user.json) never reaches the HAR
    state = json.load(open(os.path.join(PROJECTS_BASE, PROJECT, ".auth", "user.json"), encoding="utf-8"))
    sid = next(c["value"] for c in state["cookies"] if c["name"] == "sid")
    assert sid not in har_text and "sid=" not in har_text
    for path in (out["report_json"], out["mta_results"], har["path"]):
        assert "alice-pass-1" not in open(path, encoding="utf-8").read()
