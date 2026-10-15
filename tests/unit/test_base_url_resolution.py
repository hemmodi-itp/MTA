"""Phase 0.6 — base URL resolution has no localhost default; multi-module runs
are split per module; renderer pins each new spec to its module URL."""

import os
from unittest.mock import patch

import pytest
import yaml

from tools.base_url import (
    BaseUrlUnresolved,
    module_ids_of_targets,
    module_urls,
    resolve_execution_base_url,
    resolve_project_base_url,
)

TWO_MODULES = {"modules": [{"id": "M01", "url": "https://a.test/login"},
                           {"id": "M02", "url": "https://a.test/shop"}]}


def test_explicit_wins():
    assert resolve_execution_base_url("https://x.test", TWO_MODULES) == ("https://x.test", "request")


def test_project_url_then_single_module():
    assert resolve_execution_base_url(None, {"project": {"url": "https://p.test"}}) == ("https://p.test", "project.url")
    assert resolve_execution_base_url(None, {"url": "https://legacy.test"})[0] == "https://legacy.test"
    single = {"modules": [{"id": "M01", "url": "https://one.test"}, {"id": "M02", "url": "https://one.test"}]}
    assert resolve_execution_base_url(None, single) == ("https://one.test", "module.url")


def test_targeted_module_resolves_ambiguity():
    assert resolve_execution_base_url(None, TWO_MODULES, ["M02"]) == ("https://a.test/shop", "module.url")


def test_pages_of_one_app_resolve_to_its_origin():
    # every generated spec pins its own module URL (test.use({ baseURL })): the run needs only the origin
    assert resolve_execution_base_url(None, TWO_MODULES) == ("https://a.test", "module.origin")


def test_ambiguous_and_missing_fail_fast():
    two_apps = {"modules": [{"id": "M01", "url": "https://a.test/login"}, {"id": "M02", "url": "https://b.test/shop"}]}
    with pytest.raises(BaseUrlUnresolved, match="ambiguous"):
        resolve_execution_base_url(None, two_apps)
    with pytest.raises(BaseUrlUnresolved, match="unresolved"):
        resolve_execution_base_url(None, {})
    with pytest.raises(BaseUrlUnresolved):
        resolve_execution_base_url("   ", {"modules": [{"id": "M01"}]})


def test_project_base_url_helper_never_invents():
    assert resolve_project_base_url({}) == ""
    assert resolve_project_base_url(TWO_MODULES) == ""
    assert module_urls(TWO_MODULES) == {"M01": "https://a.test/login", "M02": "https://a.test/shop"}


def test_module_ids_of_targets():
    targets = [
        "application_assets/projects/p/test_creation/test_scripts/M01/test_a.spec.ts",
        "C:\\x\\test_scripts\\M02\\test_b.spec.ts",
        "application_assets/projects/p/test_creation/test_scripts/test_flat.spec.ts",
        "application_assets/projects/p/test_creation/test_scripts/M03",
    ]
    assert module_ids_of_targets(targets) == ["M01", "M02", "M03"]


# ── UIExecutionAgent integration (subprocess mocked) ─────────────────────────

def _write_project(base, name, cfg):
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "project.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)


@patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=True)
@patch("agents.test_execution.ui_execution.agent._parse_playwright_json", return_value=([], 0, 0))
@patch("agents.test_execution.ui_execution.agent._recover_partial_results", return_value=[])
@patch("agents.test_execution.ui_execution.agent._stream_proc", return_value=("", "", False, 0))
def test_multi_module_run_split_per_module(mock_stream, _rec, _parse, _inst, tmp_path, monkeypatch):
    from agents.test_execution.ui_execution import agent as ui

    monkeypatch.setattr(ui, "_ASSETS_BASE", str(tmp_path))
    _write_project(str(tmp_path), "demo", {**TWO_MODULES, "environment": "local"})
    scripts = os.path.join(str(tmp_path), "demo", "test_creation", "test_scripts")
    agent = ui.UIExecutionAgent()
    agent._run_playwright(
        project_name="demo", safe="demo", scripts_dir=scripts,
        reports_dir=os.path.join(str(tmp_path), "demo", "test_execution", "reports"),
        ts_files=["M01/test_a.spec.ts", "M02/test_b.spec.ts"], headless=True,
    )
    envs = [c.kwargs["env"] for c in mock_stream.call_args_list]
    assert sorted(e["BASE_URL"] for e in envs) == ["https://a.test/login", "https://a.test/shop"]
    assert all(e["MTA_ALLOWED_HOSTS"] == "a.test" for e in envs)
    cmds = [c.kwargs.get("cmd") or c.args[0] for c in mock_stream.call_args_list]
    assert any(any("M01" in part for part in cmd) for cmd in cmds)


@patch("agents.test_execution.ui_execution.agent._playwright_package_installed", return_value=True)
@patch("agents.test_execution.ui_execution.agent._parse_playwright_json", return_value=([], 0, 0))
@patch("agents.test_execution.ui_execution.agent._recover_partial_results", return_value=[])
@patch("agents.test_execution.ui_execution.agent._stream_proc", return_value=("", "", False, 0))
def test_single_module_project_resolves_without_request_url(mock_stream, _rec, _parse, _inst, tmp_path, monkeypatch):
    from agents.test_execution.ui_execution import agent as ui

    monkeypatch.setattr(ui, "_ASSETS_BASE", str(tmp_path))
    _write_project(str(tmp_path), "one", {"modules": [{"id": "M01", "url": "https://one.test/"}],
                                          "safety": {"allowed_hosts": ["one.test", "api.one.test"]}})
    scripts = os.path.join(str(tmp_path), "one", "test_creation", "test_scripts")
    ui.UIExecutionAgent()._run_playwright(
        project_name="one", safe="one", scripts_dir=scripts,
        reports_dir=os.path.join(str(tmp_path), "one", "reports"),
        ts_files=["M01/test_a.spec.ts"], headless=True,
    )
    env = mock_stream.call_args.kwargs["env"]
    assert env["BASE_URL"] == "https://one.test/"
    assert env["MTA_ALLOWED_HOSTS"] == "one.test,api.one.test"


def test_merge_runs_keeps_errors_and_sums():
    from agents.test_execution.ui_execution.agent import _merge_runs

    a = {"status": "success", "results": [{"x": 1}], "passed": 1, "failed": 0, "skipped": 0}
    b = {"status": "failed", "error": "boom"}
    merged = _merge_runs([a, b])
    assert merged["passed"] == 1 and merged["run_errors"] == ["boom"] and merged["status"] == "success"
    assert _merge_runs([b, {"status": "failed", "error": "x"}])["status"] == "failed"


# ── Other fallbacks removed ─────────────────────────────────────────────────

def test_fallback_script_without_url_fails_fast():
    from agents.common.failure_classifier import MissingInputError
    from agents.common.fallback_core import fallback_generate_script

    with pytest.raises(MissingInputError):
        fallback_generate_script({"scenario_id": "BS-1", "title": "t"}, [], {}, base_url="")
    ts = fallback_generate_script({"scenario_id": "BS-1", "title": "t"}, [], {}, base_url="https://ok.test")
    assert "localhost" not in ts and "https://ok.test" in ts


def test_script_generation_load_base_url_reads_modules(tmp_path, monkeypatch):
    from agents.test_creation.script_generation import agent as sg

    monkeypatch.setattr(sg, "_ASSETS_BASE", str(tmp_path))
    _write_project(str(tmp_path), "s", {"modules": [{"id": "M01", "url": "https://s.test/"}]})
    assert sg._load_base_url("s") == "https://s.test/"
    _write_project(str(tmp_path), "m", TWO_MODULES)
    assert sg._load_base_url("m") == ""
    assert "localhost" not in sg._UNKNOWN_BASE_URL_NOTE


def test_renderer_pins_module_base_url_only_for_absolute_urls():
    from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan

    plan = {"tests": [{"name": "t", "type": "positive", "steps": [{"action": "navigate"}]}]}
    scen = {"scenario_id": "BS-1", "title": "T"}
    rel = "projects/p/test_creation/test_scripts/M01/test_x.spec.ts"
    pinned = render_spec_from_plan(plan, scen, "https://m.test/a'b", rel)
    assert 'test.use({ baseURL: "https://m.test/a\'b" });' in pinned
    assert "test.use" not in render_spec_from_plan(plan, scen, "", rel)


def test_suite_orchestrator_sets_env_or_errors(tmp_path):
    from tools.suite_orchestrator import SuiteOrchestrator

    _write_project(str(tmp_path), "proj", {"modules": [{"id": "M01", "url": "https://so.test/"}]})
    orch = SuiteOrchestrator(str(tmp_path / "proj"))
    with patch("tools.suite_orchestrator.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = run.return_value.stderr = ""
        orch._run("npx playwright test x --config playwright.config.ts", 1, "test_file", "x")
    env = run.call_args.kwargs["env"]
    assert env["BASE_URL"] == "https://so.test/" and env["PW_PROJECT"] == "proj"

    _write_project(str(tmp_path), "nourl", {"project": {"name": "nourl"}})
    res = SuiteOrchestrator(str(tmp_path / "nourl"))._run("npx playwright test", 1, "test_file", "x")
    assert res["status"] == "error" and "unresolved" in res["error"]


def test_nfr_specs_get_the_shared_origin_of_the_module_urls():
    from tools.base_url import resolve_execution_base_url
    cfg = {"modules": [{"id": "M01", "url": "http://127.0.0.1:8765/login"}, {"id": "M02", "url": "http://127.0.0.1:8765/cart"}]}
    assert resolve_execution_base_url(None, cfg, ["nfr"]) == ("http://127.0.0.1:8765", "module.origin (nfr)")
    assert resolve_execution_base_url(None, cfg, ["nfr", "M02"]) == ("http://127.0.0.1:8765/cart", "module.url")
