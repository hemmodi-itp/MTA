"""Phase 4.9 — the 4-level CLI's level 3 (SuiteOrchestrator.run_suite) translates a suite into one --grep
when the suite has tags/grep, or when the legacy individual/ layout is absent (it used to find nothing)."""

import json
import subprocess

import pytest

from tools.suite_orchestrator import SuiteOrchestrator


@pytest.fixture
def project(tmp_path):
    pdir = tmp_path / "shop"
    for m, f in (("M01", "test_M01_BS_001_login.spec.ts"), ("M02", "test_M02_BS_001_list.spec.ts")):
        d = pdir / "test_creation" / "test_scripts" / m
        d.mkdir(parents=True)
        (d / f).write_text("// spec")
    (pdir / "test_creation" / "test_suite.json").write_text(json.dumps({"specs": [
        {"spec_id": "M01_BS_001", "module_id": "M01", "file": "M01/test_M01_BS_001_login.spec.ts"},
        {"spec_id": "M02_BS_001", "module_id": "M02", "file": "M02/test_M02_BS_001_list.spec.ts"}]}))
    (pdir / "test_suites").mkdir()
    (pdir / "project.yaml").write_text("project: {name: shop, url: 'http://127.0.0.1:8765'}\nenvironment: local\n")
    return pdir


def _suite(pdir, body, name="smoke"):
    (pdir / "test_suites" / f"{name}_suite.json").write_text(json.dumps(body))


def _capture(monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append({"args": args, "kw": kw})
        return subprocess.CompletedProcess(args, 0, stdout="1 passed", stderr="")
    monkeypatch.setattr("tools.suite_orchestrator.subprocess.run", fake_run)
    return calls


def test_modern_layout_runs_one_grep_over_the_suite_modules(project, monkeypatch):
    _suite(project, {"scenarios": ["M01_BS_001"], "execution": {"parallel": 3}})
    calls = _capture(monkeypatch)
    out = SuiteOrchestrator(str(project)).run_suite("smoke")
    args = calls[0]["args"]
    assert isinstance(args, list) and calls[0]["kw"].get("shell") is not True     # no cmd.exe parsing of | ( <
    assert args[1:3] == ["playwright", "test"]
    assert any(a.endswith("test_scripts/M01") for a in args) and not any(a.endswith("/M02") for a in args)
    assert "M01_BS_001" in args[args.index("--grep") + 1] and "--workers=3" in args
    assert calls[0]["kw"]["env"]["BASE_URL"] == "http://127.0.0.1:8765"
    assert out["status"] == "passed" and out["grep"]


def test_tag_suite_spans_all_modules(project, monkeypatch):
    _suite(project, {"tags": ["@smoke"]})
    calls = _capture(monkeypatch)
    SuiteOrchestrator(str(project)).run_suite("smoke", headless=False)
    args = calls[0]["args"]
    assert any(a.endswith("/test_scripts") for a in args) and "--headed" in args


def test_empty_suite_is_no_tests(project, monkeypatch):
    _suite(project, {"scenarios": ["GONE"]})
    calls = _capture(monkeypatch)
    out = SuiteOrchestrator(str(project)).run_suite("smoke")
    assert out["status"] == "no_tests" and out["unresolved"] == ["GONE"] and calls == []


def test_legacy_individual_layout_unchanged(project, monkeypatch):
    ind = project / "test_creation" / "test_scripts" / "individual"
    ind.mkdir()
    (ind / "test_SC-001_x.spec.ts").write_text("// spec")
    _suite(project, {"scenarios": ["SC-001"]})
    seen = []
    monkeypatch.setattr(SuiteOrchestrator, "_run", lambda self, cmd, level, key, value: seen.append(cmd) or
                        {"level": level, key: value, "status": "passed"})
    out = SuiteOrchestrator(str(project)).run_suite("smoke")
    assert out["test_count"] == 1 and "test_SC-001_x.spec.ts" in seen[0] and "--grep" not in seen[0]
