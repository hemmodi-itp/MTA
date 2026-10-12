"""Phase 4.7 — UIExecutionAgent: MTA reporter file is the source of truth; flaky != passed; skipped stays skipped;
browser-close -> skipped only in headed runs; headed runs never retry; safety policy reaches the runtime."""

import json
import os
import subprocess

import pytest

import agents.test_execution.ui_execution.agent as ui
from agents.test_execution.ui_execution.agent import (
    _count_flaky, _count_results, _load_results, _mark_browser_close_as_skipped, _merge_runs,
)
from agents.test_execution.ui_execution.agent import _cmd_exe_line
from tools.execution.config import effective_fail_on_flaky, effective_retries, resolve_execution_config


class _Log:
    def warning(self, *a, **k): pass
    info = error = debug = warning


def _mta_doc():
    def t(title, status, attempts):
        return {"test_id": title, "title": title, "spec_file": "shop/test_creation/test_scripts/M03/test_M03_BS_001_x.spec.ts",
                "project": "chromium", "tags": ["@P1"], "annotations": [], "tc_id": f"TC-{title}", "ac_ids": ["AC-1"],
                "status": status, "retries": len(attempts) - 1,
                "attempts": [{"retry": i, "status": s, "duration_ms": 10 * (i + 1), "error": e,
                              "failed_step": "2. Click \"save\"" if e else None} for i, (s, e) in enumerate(attempts)],
                "attachments": [], "cleanup_failures": ["product 3: 500"] if title == "p" else []}
    return {"schema_version": 2, "artifact": "mta_results", "tests": [
        t("p", "passed", [("passed", None)]),
        t("fl", "flaky", [("failed", "Timeout"), ("passed", None)]),
        t("f", "failed", [("failed", "boom"), ("failed", "boom")]),
        t("to", "timedOut", [("timedOut", "Test timeout of 60000ms exceeded")]),
        t("s", "skipped", []),
    ]}


def test_results_come_from_the_mta_file_with_flaky_and_skipped_kept(tmp_path):
    mta = tmp_path / "x.mta_results.json"
    mta.write_text(json.dumps(_mta_doc()), encoding="utf-8")
    results, source = _load_results(str(mta), str(tmp_path / "missing.json"), _Log())
    assert source == "mta_results"
    by = {r["test_title"]: r for r in results}
    assert {k: v["status"] for k, v in by.items()} == {"p": "success", "fl": "flaky", "f": "failed", "to": "failed", "s": "skipped"}
    assert by["to"]["pw_status"] == "timedOut" and by["fl"]["flaky"] is True
    assert by["fl"]["test_case_id"] == by["fl"]["business_scenario_id"] == "M03_BS_001"
    assert by["f"]["failed_step"] == '2. Click "save"' and by["p"]["cleanup_failures"] == ["product 3: 500"]
    assert _count_results(results) == (1, 2, 1) and _count_flaky(results) == 1


def test_playwright_json_is_the_fallback_with_the_same_mapping(tmp_path):
    report = {"suites": [{"specs": [{"file": "M01/test_M01_BS_001_a.spec.ts", "title": t, "tags": [], "tests": [
        {"status": st, "annotations": [], "results": [{"duration": 5}]}]} for t, st in
        (("ok", "expected"), ("flaky", "flaky"), ("bad", "unexpected"), ("skip", "skipped"))]}]}
    js = tmp_path / "r.json"
    js.write_text(json.dumps(report), encoding="utf-8")
    results, source = _load_results("", str(js), _Log())
    assert source == "playwright_json"
    assert [r["status"] for r in results] == ["success", "flaky", "failed", "skipped"]
    # an MTA file without tests (e.g. crashed reporter) also falls back
    empty = tmp_path / "e.mta_results.json"
    empty.write_text(json.dumps({"artifact": "mta_results", "tests": []}), encoding="utf-8")
    assert _load_results(str(empty), str(js), _Log())[1] == "playwright_json"


@pytest.mark.parametrize("error, headed, status, kind", [
    ("Target page, context or browser has been closed", True, "skipped", None),
    ("Target page, context or browser has been closed", False, "failed", "browser_closed"),
    ("browser has been closed", False, "failed", "browser_closed"),
    ("Target crashed", True, "failed", None),          # a crash is never "a human closed it"
    ("Target crashed", False, "failed", "browser_closed"),
    ("expect(locator).toBeVisible() failed", False, "failed", None),
])
def test_browser_close_reclassified_only_when_headed(error, headed, status, kind):
    results = [{"status": "failed", "errors": [error], "first_attempt_duration_ms": 100}]
    out, count = _mark_browser_close_as_skipped(results, headed=headed)
    assert out[0]["status"] == status and out[0].get("error_kind") == kind
    assert count == (1 if status == "skipped" else 0)


def test_merge_runs_adds_flaky():
    merged = _merge_runs([
        {"status": "success", "results": [{}], "passed": 1, "failed": 0, "skipped": 0, "flaky": 1},
        {"status": "success", "results": [{}], "passed": 2, "failed": 1, "skipped": 1, "flaky": 0},
    ])
    assert (merged["passed"], merged["flaky"], merged["failed"], merged["skipped"], merged["scenarios_executed"]) == \
        (3, 1, 1, 1, 6)


def test_effective_retries_and_fail_on_flaky():
    cfg = resolve_execution_config({})
    assert effective_retries(cfg, env={}) == 1 and effective_retries(cfg, env={"CI": "1"}) == 2
    assert effective_retries(cfg, headed=True, env={"CI": "1"}) == 0
    assert effective_retries(resolve_execution_config({"execution": {"retries": 4}}), env={}) == 4
    assert effective_fail_on_flaky(cfg, env={"CI": "true"}) is True and effective_fail_on_flaky(cfg, env={}) is False
    assert effective_fail_on_flaky(resolve_execution_config({"execution": {"fail_on_flaky_tests": True}}), env={})


# ── command line + env, through _run_playwright with a fake Playwright process ────────────────────────────

@pytest.fixture
def project(tmp_path, monkeypatch):
    base = tmp_path / "projects"
    pdir = base / "shop"
    (pdir / "test_creation" / "test_scripts" / "M01").mkdir(parents=True)
    (pdir / "test_creation" / "test_scripts" / "M01" / "test_M01_BS_001_a.spec.ts").write_text("// x")
    (pdir / "project.yaml").write_text(
        "project: {name: shop, url: 'http://127.0.0.1:9/'}\nenvironment: prod\nsafety: {allow_destructive: true}\n")
    monkeypatch.setattr(ui, "_ASSETS_BASE", str(base))
    monkeypatch.setattr(ui, "_playwright_package_installed", lambda: True)
    calls = []

    def fake_stream(cmd, cwd, env, logger):
        calls.append((cmd, env))
        mta = env.get("MTA_RESULTS_FILE")
        os.makedirs(os.path.dirname(mta), exist_ok=True)
        with open(mta, "w", encoding="utf-8") as fh:
            json.dump(_mta_doc(), fh)
        return "", "", False, 1

    monkeypatch.setattr(ui, "_stream_proc", fake_stream)
    return calls


def _run(headless=True):
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    return UIExecutionAgent().execute({"project_name": "shop", "headless": headless}, {})


def test_run_reports_flaky_separately_and_passes_the_safety_policy(project):
    out = _run()
    cmd, env = project[0]
    assert "--retries=0" not in cmd
    assert env["MTA_DESTRUCTIVE_ALLOWED"] == "0" and env["MTA_SAFETY_ENVIRONMENT"] == "prod"   # prod never allows
    assert (out["passed"], out["flaky"], out["failed"], out["skipped"]) == (1, 1, 2, 1)
    assert out["scenarios_executed"] == 5 and out["results_source"] == "mta_results"
    assert {r["test_title"]: r["status"] for r in out["results"]}["fl"] == "flaky"


def test_headed_run_never_retries(project):
    _run(headless=False)
    cmd, _ = project[0]
    assert "--headed" in cmd and "--retries=0" in cmd


def test_cmd_exe_line_quotes_metacharacters_for_npx_cmd():
    # Windows runs npx.cmd through cmd.exe: an unquoted | in a grep would become a pipe (no report, EPIPE)
    line = _cmd_exe_line([r"C:\Program Files\nodejs\npx.cmd", "playwright", "test",
                          r"C:/Users/HemModi(DataAI)/x.spec.ts", "--grep", "@smoke|@P0", "--workers=2", 'say "hi"'])
    assert line == ('"C:\\Program Files\\nodejs\\npx.cmd" playwright test "C:/Users/HemModi(DataAI)/x.spec.ts" '
                    '--grep "@smoke|@P0" --workers=2 "say ""hi"""')
