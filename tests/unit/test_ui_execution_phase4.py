"""Phase 4 — UIExecutionAgent: projects from the matrix, separate --output, JUnit/MTA/blob env, grep,
local shards + merge, CI merge_run, suite grep mode, role pre-step wiring. Playwright is never started:
_stream_proc is replaced by a recorder that writes the files Playwright would write."""

import json
import os

import pytest

import agents.test_execution.ui_execution.agent as ui
from tools.execution import config as exec_config

PW_JSON = {
    "suites": [{"title": "s", "specs": [
        {"file": "shop/test_creation/test_scripts/M01/test_M01_BS_001_login.spec.ts", "title": "AC-01.1 valid login",
         "tags": ["@P0", "@smoke"],
         "tests": [{"status": "expected", "annotations": [{"type": "tc", "description": "M01_TC_001"}],
                    "results": [{"duration": 500}]}]},
        {"file": "shop/test_creation/test_scripts/M02/test_M02_BS_001_list.spec.ts", "title": "lists products",
         "tags": ["@P2"], "tests": [{"status": "unexpected", "results": [{"duration": 700, "error": {"message": "boom"}}]}]},
    ]}]
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    base = tmp_path / "projects"
    pdir = base / "shop"
    for m, name in (("M01", "test_M01_BS_001_login.spec.ts"), ("M02", "test_M02_BS_001_list.spec.ts")):
        d = pdir / "test_creation" / "test_scripts" / m
        d.mkdir(parents=True)
        (d / name).write_text("// spec", encoding="utf-8")
    (pdir / "test_creation" / "test_suite.json").write_text(json.dumps({"specs": [
        {"spec_id": "M01_BS_001", "module_id": "M01", "file": "M01/test_M01_BS_001_login.spec.ts"},
        {"spec_id": "M02_BS_001", "module_id": "M02", "file": "M02/test_M02_BS_001_list.spec.ts"},
    ]}), encoding="utf-8")
    write_yaml(pdir, "")
    monkeypatch.setattr(ui, "_ASSETS_BASE", str(base))
    monkeypatch.setattr(exec_config.constants, "PROJECTS_BASE", str(base))
    monkeypatch.setattr(ui, "_playwright_package_installed", lambda: True)
    monkeypatch.setattr(ui, "_apply_traceability", lambda *a, **k: None)
    return pdir


def write_yaml(pdir, execution_block: str, extra: str = ""):
    (pdir / "project.yaml").write_text(
        "project: {name: shop, url: 'http://127.0.0.1:8765'}\nenvironment: local\n" + extra + execution_block,
        encoding="utf-8")


class Recorder:
    """Stands in for _stream_proc: records every call; a `test` call writes the JSON / JUnit / MTA files
    its env points at, a shard call writes its blob zip, a merge writes the merged files."""

    def __init__(self, rc=0, stdout="", pw_json=PW_JSON):
        self.calls = []
        self.rc, self.stdout, self.pw_json = rc, stdout, pw_json

    def __call__(self, cmd, cwd, env, logger, timeout=None):
        self.calls.append({"cmd": list(cmd), "env": dict(env)})
        if cmd[2] == "test" and env.get("MTA_BLOB_ONLY") == "1":
            shard = [a for a in cmd if a.startswith("--shard=")][0].split("=")[1].split("/")[0]
            os.makedirs(env["PW_BLOB_DIR"], exist_ok=True)
            open(os.path.join(env["PW_BLOB_DIR"], f"report-{shard}.zip"), "wb").write(b"zip")
        else:
            if self.pw_json is not None:
                write(env["PW_JSON_REPORT"], json.dumps(self.pw_json))
            for key, body in (("PW_JUNIT_REPORT", "<testsuites/>"), ("MTA_RESULTS_FILE", '{"artifact": "mta_results"}')):
                if env.get(key):
                    write(env[key], body)
            if env.get("PW_BLOB_DIR"):
                os.makedirs(env["PW_BLOB_DIR"], exist_ok=True)
                open(os.path.join(env["PW_BLOB_DIR"], "report-1.zip"), "wb").write(b"zip")
        return self.stdout, "", False, self.rc


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)


def run(monkeypatch, request, recorder=None):
    rec = recorder or Recorder()
    monkeypatch.setattr(ui, "_stream_proc", rec)
    out = ui.UIExecutionAgent().execute({"project_name": "shop", "headless": True, **request}, {})
    return out, rec


def flag(cmd, prefix):
    return [a for a in cmd if a.startswith(prefix)]


# ── command line + outputs ────────────────────────────────────────────────────

def test_default_run_chromium_separate_output_and_report_files(project, monkeypatch):
    out, rec = run(monkeypatch, {})
    cmd, env = rec.calls[0]["cmd"], rec.calls[0]["env"]
    assert flag(cmd, "--project=") == ["--project=chromium"]
    output = flag(cmd, "--output=")[0].split("=", 1)[1]
    assert os.path.normpath(output) != os.path.normpath(env["PW_HTML_REPORT"])       # the HTML reporter empties its folder
    assert os.sep + "test-results" + os.sep in os.path.normpath(output)
    assert env["PW_JUNIT_REPORT"].endswith(".xml") and env["MTA_RESULTS_FILE"].endswith(".mta_results.json")
    assert env["MTA_PROJECTS"] == "chromium" and env["MTA_RUN_ID"]
    assert "PW_BLOB_DIR" not in env and "--shard" not in " ".join(cmd)
    assert out["status"] == "success" and out["passed"] == 1 and out["failed"] == 1
    assert out["report_junit"] == env["PW_JUNIT_REPORT"] and out["mta_results"] == env["MTA_RESULTS_FILE"]
    assert out["projects"] == ["chromium"]
    record = json.load(open(next(
        os.path.join(dp, f) for dp, _, fs in os.walk(project / "test_execution" / "reports" / "mta")
        for f in fs if f.endswith(".execution_results.json")), encoding="utf-8"))
    assert record["mta_results"] == env["MTA_RESULTS_FILE"] and record["projects"] == ["chromium"]


def test_matrix_projects_and_browser_override(project, monkeypatch):
    write_yaml(project, "execution:\n  matrix: [chromium, firefox, Pixel 7]\n")
    _, rec = run(monkeypatch, {})
    assert flag(rec.calls[0]["cmd"], "--project=") == ["--project=chromium", "--project=firefox", "--project=pixel-7"]
    assert rec.calls[0]["env"]["MTA_PROJECTS"] == "chromium,firefox,pixel-7"
    _, rec = run(monkeypatch, {"browsers": ["webkit"]})
    assert flag(rec.calls[0]["cmd"], "--project=") == ["--project=webkit"]


def test_junit_and_mta_can_be_switched_off(project, monkeypatch):
    write_yaml(project, "execution:\n  junit: false\n  mta_reporter: false\n")
    out, rec = run(monkeypatch, {})
    env = rec.calls[0]["env"]
    assert "PW_JUNIT_REPORT" not in env and "MTA_RESULTS_FILE" not in env
    assert "report_junit" not in out and "mta_results" not in out


def test_grep_and_grep_invert(project, monkeypatch):
    out, rec = run(monkeypatch, {"grep": "@smoke|@P0", "grep_invert": "@slow"})
    cmd = rec.calls[0]["cmd"]
    assert cmd[cmd.index("--grep") + 1] == "@smoke|@P0"
    assert cmd[cmd.index("--grep-invert") + 1] == "@slow"
    assert out["grep"] == "@smoke|@P0"


def test_grep_selecting_nothing_is_skipped_not_fake_skips(project, monkeypatch):
    rec = Recorder(rc=1, stdout="Error: No tests found.\n", pw_json=None)
    out, _ = run(monkeypatch, {"grep": "@nothing"}, rec)
    assert out["status"] == "skipped" and out["results"] == [] and "No tests match" in out["reason"]


def test_missing_firefox_names_the_browser(project, monkeypatch):
    write_yaml(project, "execution:\n  matrix: [firefox]\n")
    rec = Recorder(rc=1, stdout="Error: browserType.launch: Executable doesn't exist at C:\\ms-playwright\\firefox-1490\\firefox.exe",
                   pw_json=None)
    out, _ = run(monkeypatch, {}, rec)
    assert out["status"] == "failed" and "npx playwright install firefox" in out["error"]
    assert ui._browser_missing_message("", ["chromium", "iphone-14"]).endswith(
        "`npx playwright install chromium webkit` once before executing tests (see README Quick Start).")


def test_combine_grep():
    assert ui._combine_grep("a", None) == "a" and ui._combine_grep(None, "b") == "b"
    assert ui._combine_grep(None, None) is None
    assert ui._combine_grep("x", "y") == "^(?=.*(?:x))(?=.*(?:y))"


# ── shards + merge ────────────────────────────────────────────────────────────

def test_local_shards_run_each_shard_then_merge(project, monkeypatch):
    out, rec = run(monkeypatch, {"shards": 2})
    tests = [c for c in rec.calls if c["cmd"][2] == "test"]
    merges = [c for c in rec.calls if c["cmd"][2] == "merge-reports"]
    assert [flag(c["cmd"], "--shard=") for c in tests] == [["--shard=1/2"], ["--shard=2/2"]]
    assert all(c["env"]["MTA_BLOB_ONLY"] == "1" for c in tests)
    assert len({c["env"]["PW_BLOB_DIR"] for c in tests}) == 2
    assert len({flag(c["cmd"], "--output=")[0] for c in tests}) == 2
    assert len(merges) == 1
    m = merges[0]
    assert m["cmd"][3:5] == ["--config", "playwright.merge.config.ts"]
    assert "PW_BLOB_DIR" not in m["env"] and "MTA_BLOB_ONLY" not in m["env"]
    assert m["env"]["PW_JSON_REPORT"] == out["report_json"]
    assert out["shards"] == 2 and out["passed"] == 1 and out["failed"] == 1     # totals from the merged report
    index = json.load(open(project / "test_execution" / "reports" / "index.json", encoding="utf-8"))
    assert len(index) == 1                                                      # one index entry per run


def test_shards_from_project_yaml_and_parallel_shards(project, monkeypatch):
    write_yaml(project, "execution:\n  shards: 3\n  max_parallel_shards: 3\n")
    out, rec = run(monkeypatch, {})
    assert sorted(flag(c["cmd"], "--shard=")[0] for c in rec.calls if c["cmd"][2] == "test") == \
        ["--shard=1/3", "--shard=2/3", "--shard=3/3"]
    assert out["shards"] == 3


def test_single_ci_shard_keeps_normal_reports_and_writes_a_blob(project, monkeypatch):
    out, rec = run(monkeypatch, {"shard": "2/2", "run_id": "ci-77"})
    call = rec.calls[0]
    assert flag(call["cmd"], "--shard=") == ["--shard=2/2"]
    assert os.path.basename(call["env"]["PW_BLOB_DIR"]).startswith("shard-2-")      # one folder per invocation
    assert os.path.basename(os.path.dirname(call["env"]["PW_BLOB_DIR"])) == "ci-77"
    assert "MTA_BLOB_ONLY" not in call["env"] and call["env"]["PW_JSON_REPORT"]
    assert out["shard"] == "2/2" and out["run_id"] == "ci-77"
    assert not [c for c in rec.calls if c["cmd"][2] == "merge-reports"]


def test_merge_run_merges_ci_blobs(project, monkeypatch):
    for i in (1, 2):
        d = project / "test_execution" / "reports" / "blob" / "ci-77" / f"shard-{i}"
        d.mkdir(parents=True)
        (d / f"report-{i}.zip").write_bytes(b"z")
    out, rec = run(monkeypatch, {"merge_run": "ci-77"})
    assert [c["cmd"][2] for c in rec.calls] == ["merge-reports"]
    assert out["status"] == "success" and out["passed"] == 1 and out["shards"] == 2


def test_merge_run_without_blobs_fails_clearly(project, monkeypatch):
    out, rec = run(monkeypatch, {"merge_run": "nope"})
    assert out["status"] == "failed" and "No blob reports" in out["error"] and rec.calls == []


def test_invalid_shard_fails_before_running(project, monkeypatch):
    out, rec = run(monkeypatch, {"shard": "3/2"})
    assert out["status"] == "failed" and "invalid shard" in out["error"] and rec.calls == []


def test_headed_and_healing_reruns_never_shard(project, monkeypatch):
    _, rec = run(monkeypatch, {"shards": 2, "headless": False})
    assert not any(flag(c["cmd"], "--shard=") for c in rec.calls)
    _, rec = run(monkeypatch, {"shards": 2, "spec_files": ["M01/test_M01_BS_001_login.spec.ts"]})
    assert not any(flag(c["cmd"], "--shard=") for c in rec.calls)


# ── suites ────────────────────────────────────────────────────────────────────

def _suite(project, body):
    (project / "test_suites").mkdir(exist_ok=True)
    (project / "test_suites" / "smoke_suite.json").write_text(json.dumps(body), encoding="utf-8")


def test_suite_files_mode_is_the_default(project, monkeypatch):
    _suite(project, {"scenarios": ["M01_BS_001"]})
    _, rec = run(monkeypatch, {"suite": "smoke"})
    cmd = rec.calls[0]["cmd"]
    assert any(a.endswith("test_M01_BS_001_login.spec.ts") for a in cmd) and "--grep" not in cmd


def test_suite_grep_mode_runs_one_grep_over_the_suite_modules(project, monkeypatch):
    write_yaml(project, "execution:\n  suite_mode: grep\n")
    _suite(project, {"scenarios": ["M01_BS_001", {"id": "M02_BS_001", "grep": "lists"}, "GONE_1"]})
    out, rec = run(monkeypatch, {"suite": "smoke"})
    assert len([c for c in rec.calls if c["cmd"][2] == "test"]) == 1          # one process, not one per entry
    cmd = rec.calls[0]["cmd"]
    grep = cmd[cmd.index("--grep") + 1]
    assert "M01_BS_001" in grep and "M02_BS_001" in grep
    targets = [a for a in cmd if a.endswith("/M01") or a.endswith("/M02")]
    assert len(targets) == 2                                                   # module folders, not every file
    assert out["suite_unresolved"] == ["GONE_1"] and out["suite_grep"] == grep


def test_suite_grep_mode_tags_and_empty_suite(project, monkeypatch):
    write_yaml(project, "execution:\n  suite_mode: grep\n")
    _suite(project, {"tags": ["@smoke"]})
    _, rec = run(monkeypatch, {"suite": "smoke", "grep": "@P0"})
    cmd = rec.calls[0]["cmd"]
    assert cmd[cmd.index("--grep") + 1].startswith("^(?=.*(?:")                # suite AND request grep
    _suite(project, {"scenarios": ["GONE_1"]})
    out, rec = run(monkeypatch, {"suite": "smoke"})
    assert out["status"] == "skipped" and rec.calls == []


def test_grep_targets_helper(tmp_path):
    for rel in ("M01/a.spec.ts", "M01/b.spec.ts", "M02/c.spec.ts", "flat.spec.ts"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    targets, files = ui._grep_targets(str(tmp_path), [])
    assert len(targets) == 3 and len(files) == 4
    targets, files = ui._grep_targets(str(tmp_path), ["M02"])
    assert targets == [str(tmp_path / "M02").replace(os.sep, "/")] and files == [os.path.join("M02", "c.spec.ts")]


def test_recovery_never_invents_entries_for_folder_targets(tmp_path):
    rows = ui._recover_partial_results(["M01", "M01/x.spec.ts"], str(tmp_path / "none.json"), "", ui.get_logger("t"))
    assert [r["spec_file"] for r in rows] == ["M01/x.spec.ts"]


def test_merge_runs_keeps_every_sub_runs_files():
    runs = [{"status": "success", "results": [], "passed": 1, "failed": 0, "skipped": 0,
             "mta_results": f"m{i}.json", "report_junit": f"j{i}.xml", "report_json": f"r{i}.json"} for i in (1, 2)]
    out = ui._merge_runs(runs)
    assert out["mta_results_all"] == ["m1.json", "m2.json"] and out["report_junit_all"] == ["j1.xml", "j2.xml"]


# ── role pre-step ─────────────────────────────────────────────────────────────

ROLES_YAML = ("auth:\n  enabled: false\n  roles:\n    user: {strategy: setup, steps: [{goto: 'http://127.0.0.1:8765/login'}]}\n"
              "    guest: {anonymous: true}\n")


def test_role_auth_runs_once_per_execute_when_enabled(project, monkeypatch):
    calls = []

    def fake_ensure(safe, roles, max_age_minutes=30, **kw):
        calls.append((safe, [r.name for r in roles], max_age_minutes))
        return {"dir": "x", "roles": [{"name": "user", "status": "captured"}], "failed": []}

    monkeypatch.setattr("tools.auth.role_states.ensure_role_states", fake_ensure)
    write_yaml(project, "execution:\n  role_auth: true\n  role_auth_max_age_minutes: 5\n", extra=ROLES_YAML)
    # two modules with different URLs and no project.url -> per-module split -> two Playwright runs
    (project / "project.yaml").write_text(
        "project: {name: shop}\nenvironment: local\nmodules:\n  - {id: M01, url: 'http://127.0.0.1:8765/login'}\n"
        "  - {id: M02, url: 'http://127.0.0.1:8765/products'}\n" + ROLES_YAML
        + "execution:\n  role_auth: true\n  role_auth_max_age_minutes: 5\n", encoding="utf-8")
    out, rec = run(monkeypatch, {})
    assert len([c for c in rec.calls if c["cmd"][2] == "test"]) == 2
    assert calls == [("shop", ["user", "guest"], 5)]
    assert out["role_auth"]["roles"][0]["status"] == "captured"


def test_role_auth_off_by_default(project, monkeypatch):
    monkeypatch.setattr("tools.auth.role_states.ensure_role_states",
                        lambda *a, **k: pytest.fail("role auth must not run when execution.role_auth is false"))
    write_yaml(project, "", extra=ROLES_YAML)
    out, _ = run(monkeypatch, {})
    assert "role_auth" not in out
