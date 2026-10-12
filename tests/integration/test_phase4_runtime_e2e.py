"""
Phase 4 acceptance, end to end on the buggy_shop benchmark app (real Chromium, real Playwright 1.64,
through UIExecutionAgent — no mocks):

  * AC4 — JUnit XML and the MTA reporter output are produced; MTA output links tests to TC/AC ids.
  * AC5 — per-role auth: two logged-in roles (user, admin; `setup` strategy) + anonymous (guest).
  * AC6 — a 2-shard run merged with merge-reports has the same totals as an unsharded run.
  * plus: suite → grep translation runs one process; failure evidence survives the HTML report.

Run:  python -m pytest tests/integration/test_phase4_runtime_e2e.py -v -s
Skipped when node_modules/playwright or the buggy_shop app cannot start.
"""

import json
import os
import shutil
import socket
import xml.etree.ElementTree as ET

import pytest

from tools.constants import PROJECTS_BASE

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPECS = os.path.join(ROOT, "tests", "e2e", "phase4")
PROJECT = "bench_p4_e2e"          # bench_* is gitignored

pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(ROOT, "node_modules", "playwright", "lib", "program.js")),
    reason="npm install has not been run")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _yaml(base_url: str) -> str:
    login = [f"        - goto: {base_url}/login",
             "        - fill: {selector: '#username', value: %s}",
             "        - fill: {selector: '#password', value: %s}",
             "        - click: '#login-button'"]
    user = "\n".join(login) % ("alice", "alice-pass-1")
    admin = "\n".join(login) % ("admin", "admin-pass-1")
    return f"""project:
  name: {PROJECT}
  url: {base_url}
environment: local
safety:
  allowed_hosts: [127.0.0.1]
auth:
  enabled: false
  roles:
    user:
      strategy: setup
      steps:
{user}
    admin:
      strategy: setup
      steps:
{admin}
    guest:
      anonymous: true
execution:
  role_auth: true
  suite_mode: grep
"""


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
    scripts = os.path.join(pdir, "test_creation", "test_scripts", "P4")
    os.makedirs(scripts)
    for f in os.listdir(SPECS):
        shutil.copy(os.path.join(SPECS, f), scripts)
    with open(os.path.join(pdir, "project.yaml"), "w", encoding="utf-8") as fh:
        fh.write(_yaml(server.base_url))
    os.makedirs(os.path.join(pdir, "test_suites"))
    with open(os.path.join(pdir, "test_suites", "roles_suite.json"), "w", encoding="utf-8") as fh:
        json.dump({"suite_id": "roles", "tags": ["@roles"]}, fh)
    yield pdir
    server.stop()
    if not os.environ.get("MTA_KEEP_E2E"):
        shutil.rmtree(pdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _real_projects_base(_isolate_projects_base, monkeypatch):
    """tests/conftest.py points every PROJECTS_BASE alias at a temp folder. This test drives the real
    Playwright runner, which reads project.yaml, the specs and .auth/ from application_assets/projects/
    under the repo root — so the aliases this run touches go back to the real (gitignored bench_*) path."""
    import tools.constants as constants
    import agents.test_execution.ui_execution.agent as ui
    monkeypatch.setattr(constants, "PROJECTS_BASE", PROJECTS_BASE)
    monkeypatch.setattr(ui, "_ASSETS_BASE", PROJECTS_BASE)
    monkeypatch.chdir(ROOT)


def _execute(**request):
    from agents.test_execution.ui_execution.agent import UIExecutionAgent

    return UIExecutionAgent().execute({"project_name": PROJECT, "headless": True, **request}, {})


def _by_title(out):
    return {r["test_title"]: r["status"] for r in out["results"]}


def test_unsharded_run_roles_reporters_and_evidence(shop):
    out = _execute()
    print(json.dumps({k: out.get(k) for k in ("status", "passed", "failed", "skipped", "projects",
                                               "report_junit", "mta_results", "role_auth")}, indent=2, default=str))
    statuses = _by_title(out)
    # AC5 — every role behaves as its permissions say
    for title in ("admin reaches the admin page", "user is denied the admin page",
                  "user sees the product list without logging in again", "guest is sent to the login page"):
        assert statuses[title] == "success", title
    role_status = {r["name"]: r["status"] for r in out["role_auth"]["roles"]}
    assert role_status["user"] in ("captured", "reused") and role_status["admin"] in ("captured", "reused")
    assert role_status["guest"] == "anonymous" and out["role_auth"]["failed"] == []
    assert statuses["a deliberately failing check shows up as failed with evidence"] == "failed"
    assert (out["passed"], out["failed"]) == (9, 1)

    # AC4 — JUnit XML
    suites = ET.parse(out["report_junit"]).getroot()
    assert int(suites.get("tests")) == 10 and int(suites.get("failures")) == 1
    # AC4 — MTA reporter output, linked to TC / AC ids, valid against its contract
    from contracts.artifacts.io import validate_file
    assert validate_file("mta_results", out["mta_results"]).ok
    doc = json.load(open(out["mta_results"], encoding="utf-8"))
    tests = {t["title"]: t for t in doc["tests"]}
    admin = tests["admin reaches the admin page"]
    assert admin["tc_id"] == "P4_TC_001" and admin["ac_ids"] == ["AC-06.1"] and admin["status"] == "passed"
    assert "@roles" in admin["tags"] and admin["project"] == "chromium"
    failing = tests["a deliberately failing check shows up as failed with evidence"]
    assert failing["status"] == "failed" and failing["ac_ids"] == ["AC-99.1"]
    # retain-on-failure evidence exists on disk after the HTML report was written (F7 fix)
    kinds = {a["name"] for a in failing["attachments"] if a["path"] and os.path.exists(a["path"])}
    assert {"screenshot", "trace", "video"} <= kinds, failing["attachments"]
    assert doc["totals"]["passed"] == 9 and doc["totals"]["failed"] == 1
    # credentials never reach the reports
    for path in (out["report_json"], out["report_junit"], out["mta_results"]):
        assert "admin-pass-1" not in open(path, encoding="utf-8").read()


def test_two_shards_merged_equal_the_unsharded_totals(shop):
    unsharded = _execute()
    sharded = _execute(shards=2)
    print("unsharded", unsharded["passed"], unsharded["failed"], "| sharded", sharded["passed"], sharded["failed"],
          "| blob", sharded.get("blob_dir"))
    assert sharded["shards"] == 2 and sharded["status"] == "success"
    assert (sharded["passed"], sharded["failed"], sharded["skipped"]) == \
        (unsharded["passed"], unsharded["failed"], unsharded["skipped"])
    assert _by_title(sharded) == _by_title(unsharded)
    zips = [f for _, _, fs in os.walk(sharded["blob_dir"]) for f in fs if f.endswith(".zip")]
    assert len([z for z in zips if "_merge_input" not in z]) >= 2
    merged = json.load(open(sharded["mta_results"], encoding="utf-8"))
    assert merged["totals"]["total"] == len(unsharded["results"])
    assert int(ET.parse(sharded["report_junit"]).getroot().get("tests")) == len(unsharded["results"])


def test_ci_style_shards_then_merge_run(shop):
    a = _execute(shard="1/2", run_id="ci-e2e")
    b = _execute(shard="2/2", run_id="ci-e2e")
    merged = _execute(merge_run="ci-e2e")
    assert a["shard"] == "1/2" and b["shard"] == "2/2"
    assert merged["status"] == "success"
    assert merged["passed"] + merged["failed"] == a["passed"] + a["failed"] + b["passed"] + b["failed"] == 10


def test_suite_by_tag_and_grep(shop):
    out = _execute(suite="roles")                       # test_suites/roles_suite.json: tags [@roles]
    assert sorted(_by_title(out)) == sorted([
        "admin reaches the admin page", "user is denied the admin page",
        "user sees the product list without logging in again", "guest is sent to the login page"])
    smoke = _execute(grep="@smoke")
    assert sorted(_by_title(smoke)) == ["login page renders", "user sees the product list without logging in again"]
