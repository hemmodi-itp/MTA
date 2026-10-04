"""
conftest.py — isolates every test's filesystem writes away from the real
application_assets/projects/ directory, without dragging the legacy agent
stack into tests that don't use it.

Root cause this fixes: tools/constants.py hardcodes
    PROJECTS_BASE = os.path.join("application_assets", "projects")
and ~18 legacy agent/tool modules import it by value at module-load time
(`from tools.constants import PROJECTS_BASE as _ASSETS_BASE`). Any test that
exercises a real legacy agent's execute() with placeholder project names
("proj", "project", "my_project", "unknown", ...) would otherwise write real
files into the real project directory.

Patching tools.constants.PROJECTS_BASE alone does not reach those already-bound
aliases, so each is patched individually (_ALIASED_CONSTANTS). If a new module
aliases PROJECTS_BASE at import time, add its (module, attribute) pair below.

Scoping:
  - Tests marked `mta` (every file in _MTA_TEST_FILES, auto-marked at collection,
    or any test decorated with @pytest.mark.mta) exercise the MTA evaluation
    stack (engines/, agents/evaluation, the MTA agents). For them the fixture
    only patches modules that are ALREADY imported — it never imports the legacy
    Playwright/ADK agent stack just to patch it.
  - Every other test is treated as `legacy`: all aliases are imported and
    patched (fail-safe default — a new legacy test is protected automatically).
"""

import importlib
import os
import sys

import pytest

_ALIASED_CONSTANTS = [
    ("agents.orchestrator.agent", "_PROJECTS_DIR"),
    ("agents.test_execution.ui_execution.agent", "_ASSETS_BASE"),
    ("agents.comprehension.discovery.agent", "_ASSETS_BASE"),
    ("agents.test_execution.reporting.agent", "_ASSETS_BASE"),
    ("agents.comprehension.comprehension_agent.agent", "_ASSETS_BASE"),
    ("tools.context.artifact_context", "_ASSETS_BASE"),
    ("agents.test_execution.locator.agent", "_ASSETS_BASE"),
    ("agents.test_creation.artifact_generator.agent", "_ASSETS_BASE"),
    ("agents.test_creation.script_generation.agent", "_ASSETS_BASE"),
    ("agents.test_creation.testdata.agent", "_ASSETS_BASE"),
    ("tools.config.test_generation_config", "_ASSETS_BASE"),
    ("agents.test_execution.healing.agent", "_ASSETS_BASE"),
    ("tools.auth.auth_setup", "_ASSETS_BASE"),
    ("tools.catalog.catalog_manager", "_ASSETS_BASE"),
    ("tools.project_manifest", "_PROJECTS_DIR"),
    ("agents.test_creation.semantic_map.agent", "_ASSETS_BASE"),
    ("tools.state.project_state_manager", "_ASSETS_BASE"),
    ("tools.discovery.record_cli", "_ASSETS_BASE"),
]

# Test files that exercise only the MTA evaluation stack (api/pipeline.py →
# workflows/agent_evaluation.yaml) or shared infrastructure, never a legacy agent.
_MTA_TEST_FILES = {
    "test_action_generation.py",
    "test_agent_registry.py",
    "test_app_classification.py",
    "test_brd_compliance.py",
    "test_evidence_collection.py",
    "test_final_report.py",
    "test_mta_evaluation_core.py",
    "test_output_validation.py",
    "test_pass_fail.py",
    "test_playwright_executor.py",
    "test_runtime_discovery.py",
}


def pytest_configure(config):
    config.addinivalue_line("markers", "mta: MTA evaluation-stack test — the legacy agent stack is not imported")
    config.addinivalue_line("markers", "legacy: legacy CLI pipeline test (default for unmarked tests)")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.get_closest_marker("mta") or item.get_closest_marker("legacy"):
            continue
        if os.path.basename(str(item.fspath)) in _MTA_TEST_FILES:
            item.add_marker(pytest.mark.mta)
        else:
            item.add_marker(pytest.mark.legacy)


@pytest.fixture(autouse=True)
def _isolate_projects_base(request, tmp_path, monkeypatch):
    """Redirect every known PROJECTS_BASE binding to a per-test tmp dir so no
    test can write into the real application_assets/projects/."""
    isolated = str(tmp_path / "projects")
    os.makedirs(isolated, exist_ok=True)

    monkeypatch.setattr("tools.constants.PROJECTS_BASE", isolated, raising=False)

    import_legacy = request.node.get_closest_marker("mta") is None
    for module_name, attr in _ALIASED_CONSTANTS:
        module = sys.modules.get(module_name)
        if module is None and import_legacy:
            try:
                module = importlib.import_module(module_name)
            except Exception:
                # Optional/heavy deps (e.g. google-adk) may not be installed in
                # every environment — a module that can't import can't write
                # anywhere, so there's nothing to isolate.
                module = None
        if module is not None and hasattr(module, attr):
            monkeypatch.setattr(module, attr, isolated, raising=False)

    yield isolated
