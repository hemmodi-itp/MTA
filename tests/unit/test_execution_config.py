"""Phase 4 — `execution:` block resolution (tools/execution/config.py), shared cases with the TS builder."""

import json
import os

import pytest

from tools.execution import config as ec
from tools.execution.config import KNOWN_PROJECTS, project_slug, resolve_execution_config, resolve_projects

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CASES = json.load(open(os.path.join(ROOT, "tests", "fixtures", "execution_config_cases.json"), encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_cases_match(case):
    # The same file is asserted by application_assets/_shared/runtime/config/buildConfig.test.ts,
    # so Python (UIExecutionAgent) and TypeScript (playwright.config.ts) resolve identically.
    assert resolve_execution_config(case["project"]) == case["expected"]


def test_defaults_keep_todays_behaviour():
    cfg = resolve_execution_config({})
    assert cfg["projects"] == ["chromium"]
    assert cfg["suite_mode"] == "files"
    assert cfg["role_auth"] is False
    assert cfg["shards"] == 1
    assert cfg["test_id_attribute"] == "data-testid"
    assert cfg["trace"] == cfg["video"] == "retain-on-failure"


def test_project_names_are_slugs_the_list_regex_accepts():
    import re
    for name in KNOWN_PROJECTS:
        assert re.fullmatch(r"[\w\-]+", name)
    assert project_slug("Pixel 7") == "pixel-7"
    assert project_slug(" iPhone_14 ") == "iphone-14"


def test_chromium_always_first_and_known_order():
    assert resolve_projects(["iphone-14", "firefox"], None) == ["chromium", "firefox", "iphone-14"]
    assert resolve_projects([], "standard") == ["chromium"]
    assert resolve_projects(["webkit"], "smoke") == ["chromium"]


def test_invalid_values_warn(caplog):
    with caplog.at_level("WARNING", logger="workflow.execution"):
        cfg = resolve_execution_config({"execution": {"shards": 100, "video": "sometimes"}})
    assert cfg["shards"] == 1 and cfg["video"] == "retain-on-failure"
    assert sum("execution." in r.message for r in caplog.records) == 2


def test_float_integer_accepted_bool_rejected_for_ints():
    assert resolve_execution_config({"execution": {"shards": 3.0}})["shards"] == 3
    assert resolve_execution_config({"execution": {"shards": True}})["shards"] == 1


def test_load_execution_config_reads_project_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(ec.constants, "PROJECTS_BASE", str(tmp_path))
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "project.yaml").write_text(
        "execution:\n  test_id_attribute: data-test\n  matrix: [firefox]\n", encoding="utf-8")
    cfg = ec.load_execution_config("shop")
    assert cfg["test_id_attribute"] == "data-test"
    assert cfg["projects"] == ["chromium", "firefox"]
    assert ec.load_execution_config("missing")["projects"] == ["chromium"]


def test_manifest_carries_execution_block(tmp_path, monkeypatch):
    import tools.project_manifest as pm
    monkeypatch.setattr(pm, "_PROJECTS_DIR", str(tmp_path))
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "project.yaml").write_text(
        "project: {name: shop, url: http://127.0.0.1:1}\nenvironment: local\nexecution: {suite_mode: grep}\n",
        encoding="utf-8")
    flat = pm.load_project_manifest("shop")
    assert flat["execution"]["suite_mode"] == "grep"
    assert flat["execution"]["projects"] == ["chromium"]


def test_sauce_labs_keeps_data_test():
    # Migration (design §6): saucedemo uses data-test, so the project says so explicitly.
    import yaml
    path = os.path.join(ROOT, "application_assets", "projects", "sauceLabs", "project.yaml")
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    assert resolve_execution_config(raw)["test_id_attribute"] == "data-test"
