"""
Integration tests for SuiteOrchestrator.

Tests verify discovery logic (list_*) and the error-path behaviours
(not-found scenarios) without requiring a live browser or Playwright.
"""

import json
from pathlib import Path

import pytest

from tools.suite_orchestrator import SuiteOrchestrator

PROJECT_DIR = "application_assets/projects/AppEvolve"


@pytest.fixture
def orch() -> SuiteOrchestrator:
    return SuiteOrchestrator(PROJECT_DIR)


# ── Discovery tests ────────────────────────────────────────────────────────

class TestListSuites:
    def test_smoke_suite_discoverable(self, orch):
        assert "smoke" in orch.list_suites()

    def test_regression_suite_discoverable(self, orch):
        assert "regression" in orch.list_suites()

    def test_module_navigation_suite_discoverable(self, orch):
        assert "module_navigation" in orch.list_suites()

    def test_returns_sorted_list(self, orch):
        suites = orch.list_suites()
        assert suites == sorted(suites)


class TestListModules:
    def test_module_dirs_present(self, orch):
        """Module directories are created by the test generator; may be empty now."""
        modules = orch.list_modules()
        # All returned names must start with 'module_'
        assert all(m.startswith("module_") for m in modules)

    def test_returns_sorted_list(self, orch):
        modules = orch.list_modules()
        assert modules == sorted(modules)


class TestListWorkflows:
    def test_returns_list(self, orch):
        workflows = orch.list_workflows()
        assert isinstance(workflows, list)


# ── Error-path tests ───────────────────────────────────────────────────────

class TestNotFound:
    def test_individual_test_not_found(self, orch):
        result = orch.run_individual_test("test_NONEXISTENT.spec.ts")
        assert result["status"] == "error"
        assert result["level"] == 1
        assert "Not found" in result["error"]

    def test_module_not_found(self, orch):
        result = orch.run_module("module_nonexistent")
        assert result["status"] == "error"
        assert result["level"] == 2

    def test_suite_not_found(self, orch):
        result = orch.run_suite("nonexistent_suite")
        assert result["status"] == "error"
        assert result["level"] == 3

    def test_workflow_not_found(self, orch):
        result = orch.run_workflow("nonexistent_workflow")
        assert result["status"] == "error"
        assert result["level"] == 4


# ── Suite JSON content tests ───────────────────────────────────────────────

class TestSuiteJsonContent:
    def _load(self, suite_id: str) -> dict:
        path = Path(PROJECT_DIR) / "test_suites" / f"{suite_id}_suite.json"
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_smoke_has_all_scenarios(self):
        cfg = self._load("smoke")
        assert cfg["suite_id"] == "smoke"
        assert set(cfg["scenarios"]) == {"SC-001", "SC-002", "SC-003"}

    def test_regression_all_modules_flag(self):
        cfg = self._load("regression")
        assert cfg["all_modules"] is True

    def test_module_navigation_scope(self):
        cfg = self._load("module_navigation")
        assert cfg["scope"] == "module_navigation"
        assert "SC-002" in cfg["scenarios"]


# ── Scenario manifest tests ────────────────────────────────────────────────

class TestScenarioManifest:
    def _load_manifest(self) -> dict:
        path = Path(PROJECT_DIR) / "comprehension" / "business_scenarios_manifest.json"
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_total_scenario_count(self):
        manifest = self._load_manifest()
        assert manifest["total_scenarios"] == 3

    def test_all_modules_present(self):
        manifest = self._load_manifest()
        assert "dashboard" in manifest["modules"]
        assert "navigation" in manifest["modules"]
        assert "interaction" in manifest["modules"]

    def test_module_files_referenced(self):
        manifest = self._load_manifest()
        for module, rel_path in manifest["module_files"].items():
            full_path = Path(PROJECT_DIR) / "comprehension" / rel_path
            assert full_path.exists(), f"Missing: {full_path}"
