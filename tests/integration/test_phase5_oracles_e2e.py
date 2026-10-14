"""
Phase 5 acceptance, end to end on the buggy_shop benchmark app (real Chromium, real Playwright, through
UIExecutionAgent). The spec is rendered from JSON plans by the real spec_renderer, so the oracle actions are
exercised exactly as generated tests use them.

  * False-pass check (plan 5, acceptance): BUG_18 turns "name is required" into a silent no-op. The negative
    test with strong oracles (error text + verifyNoRequest + verifyFieldInvalid + verifyValidationMessage + URL)
    FAILS under BUG_18; the same test with a weak oracle still passes — and the linter flags that one as weak.
  * On the bug-free build every oracle test passes: verifyRequest (3xx + bodyContains), reloadAndVerify,
    verifyApiState (grey-box), verifyResponseSchema, verifyStorage, verifyAriaSnapshot, mockRoute, and the
    renderer-appended verifyNoNewConsoleErrors.

Run:  python -m pytest tests/integration/test_phase5_oracles_e2e.py -v -s
Skipped when node_modules/playwright or the buggy_shop app cannot start.
"""

import json
import os
import shutil
import socket
import time

import pytest

from tools.constants import PROJECTS_BASE
from tools.test_creation import assertion_linter
from tools.test_creation.script_generator.compose import inject_role
from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROJECT = "bench_p5_e2e"          # bench_* is gitignored
SPEC_REL = f"projects/{PROJECT}/test_creation/test_scripts/P5/test_P5_BS_001_oracles.spec.ts"

pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(ROOT, "node_modules", "playwright", "lib", "program.js")),
    reason="npm install has not been run")

STRONG = "empty name is rejected (strong oracles)"
WEAK = "empty name is rejected (weak oracle)"
NAME = f"P5 Lamp {int(time.time())}"

FILL_REST = [{"action": "navigate", "value": "/products/new"},
             {"action": "enterText", "locator_key": "price", "value": "9.99"},
             {"action": "selectDropdownByText", "locator_key": "category", "value": "Books"},
             {"action": "click", "locator_key": "save_product"}]

PLAN = {"tests": [
    {"name": STRONG, "type": "negative", "steps": FILL_REST + [
        {"action": "verifyContainsText", "locator_key": "form_errors", "value": "Name is required"},
        {"action": "verifyNoRequest", "method": "POST", "urlPattern": "/products"},
        {"action": "verifyFieldInvalid", "locator_key": "name"},
        {"action": "verifyValidationMessage", "locator_key": "name", "value": "fill"},
        {"action": "verifyUrlContains", "value": "/products/new"}]},
    {"name": WEAK, "type": "negative", "steps": FILL_REST + [
        {"action": "verifyVisible", "locator_key": "main"}]},
    {"name": "create product proves the backend", "type": "positive", "steps": [
        {"action": "navigate", "value": "/products/new"},
        {"action": "enterText", "locator_key": "name", "value": NAME},
        *FILL_REST[1:],
        {"action": "verifyContainsText", "locator_key": "flash", "value": "Product created"},
        {"action": "verifyRequest", "method": "POST", "urlPattern": "/products", "status": "3xx",
         "bodyContains": "price=9.99"},
        {"action": "reloadAndVerify", "steps": [
            {"action": "verifyText", "locator_key": "product_name", "value": NAME}]},
        {"action": "verifyApiState", "url": f"/api/products?q={NAME.replace(' ', '+')}",
         "expect": {"status": 200, "path": "total", "equals": 1}}]},
    {"name": "api list matches its schema and the session cookie is httpOnly", "type": "positive", "steps": [
        {"action": "navigate", "value": "/api/products"},
        {"action": "verifyResponseSchema", "urlPattern": "/api/products", "schema": {
            "type": "object", "required": ["items", "total", "page"],
            "properties": {"items": {"type": "array", "items": {
                "type": "object", "required": ["id", "name", "price"],
                "properties": {"id": {"type": "integer"}, "name": {"type": "string", "minLength": 1}}}},
                "total": {"type": "integer", "minimum": 0}}}},
        {"action": "verifyStorage", "store": "cookie", "key": "sid", "rule": "httpOnly"},
        {"action": "verifyStorage", "store": "cookie", "key": "sid", "rule": "sameSite"}]},
    {"name": "main navigation structure", "type": "positive", "steps": [
        {"action": "navigate", "value": "/products"},
        {"action": "verifyAriaSnapshot", "locator_key": "main_nav",
         "value": '- list:\n  - listitem:\n    - link "Products"'}]},
    {"name": "a failing backend is shown, not swallowed (fault injection)", "type": "positive", "steps": [
        {"action": "mockRoute", "urlPattern": "/api/products", "status": 503, "body": {"error": "maintenance"}},
        {"action": "navigate", "value": "/api/products"},
        {"action": "verifyContainsText", "locator_key": "body", "value": "maintenance"},
        {"action": "verifyRequest", "method": "GET", "urlPattern": "/api/products", "status": 503}]},
]}

PAGES_TS = """import { Page, Locator } from '@playwright/test';

export class P5Page {
  constructor(private readonly page: Page) {}
  get name(): Locator { return this.page.getByTestId('name'); }
  get price(): Locator { return this.page.getByTestId('price'); }
  get category(): Locator { return this.page.getByTestId('category'); }
  get save_product(): Locator { return this.page.getByTestId('save-product'); }
  get form_errors(): Locator { return this.page.getByTestId('form-errors'); }
  get flash(): Locator { return this.page.getByTestId('flash'); }
  get product_name(): Locator { return this.page.getByTestId('product-name'); }
  get main(): Locator { return this.page.getByTestId('main'); }
  get main_nav(): Locator { return this.page.getByTestId('main-nav'); }
  get body(): Locator { return this.page.locator('body'); }
}

export const PAGE_REGISTRY = { _default: P5Page };
"""


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
oracles:
  enabled: true
execution:
  role_auth: true
  role_auth_max_age_minutes: 0
  console_guard: warn
  network: on-failure
  test_steps: true
"""


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2))


def _project(base_url: str) -> str:
    pdir = os.path.join(PROJECTS_BASE, PROJECT)
    shutil.rmtree(pdir, ignore_errors=True)
    spec = render_spec_from_plan(PLAN, {"scenario_id": "P5_BS_001", "title": "Phase 5 oracles"}, base_url, SPEC_REL,
                                 project=PROJECT, test_steps=True, oracles=True)
    _write(os.path.join(ROOT, "application_assets", SPEC_REL), inject_role(spec, "user"))
    _write(os.path.join(pdir, "test_creation", "pages.ts"), PAGES_TS)
    _write(os.path.join(pdir, "project.yaml"), _yaml(base_url))
    _write(os.path.join(pdir, "test_creation", "test_suite.json"), {
        "schema_version": 2, "artifact": "test_suite", "project": PROJECT,
        "specs": [{"spec_id": "P5_BS_001", "file": "P5/test_P5_BS_001_oracles.spec.ts", "module_id": "P5",
                   "status": "new", "last_result": None}]})
    return pdir


@pytest.fixture(autouse=True)
def _real_projects_base(_isolate_projects_base, monkeypatch):
    """The real Playwright runner reads application_assets/projects/ under the repo root (see the 4b e2e)."""
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


def _run(bugs):
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS

    try:
        server = AppServer(APPS["buggy_shop"], port=_free_port(), bugs=bugs).start()
    except Exception as exc:  # pragma: no cover — environment
        pytest.skip(f"buggy_shop did not start: {exc}")
    try:
        pdir = _project(server.base_url)
        out = UIExecutionAgent().execute({"project_name": PROJECT, "headless": True}, {})
        statuses = {r["test_title"].replace(" @regression", "").replace(" @smoke", ""): r["status"]
                    for r in out["results"]}
        print(json.dumps(statuses, indent=2))
        return statuses, out
    finally:
        server.stop()
        if not os.environ.get("MTA_KEEP_E2E"):
            shutil.rmtree(os.path.join(PROJECTS_BASE, PROJECT), ignore_errors=True)


def test_linter_flags_the_weak_negative_and_passes_the_strong_one():
    by_name = {r["name"]: r for r in assertion_linter.lint_plan(PLAN)["results"]}
    assert by_name[WEAK]["weak"] and not by_name[STRONG]["weak"]
    assert all(not r["weak"] for n, r in by_name.items() if n != WEAK), by_name


def test_bug_free_build_every_oracle_test_passes():
    statuses, _ = _run([])
    assert len(statuses) == len(PLAN["tests"])
    assert all(s == "success" for s in statuses.values()), statuses


def test_false_pass_check_bug_18_fails_the_strong_negative_only():
    statuses, out = _run(["BUG_18"])
    assert statuses[STRONG] == "failed", statuses
    assert statuses[WEAK] == "success", "the weak oracle passes on a broken build — that is the false pass"
    errors = " ".join(" ".join(r.get("errors") or []) for r in out["results"] if STRONG in r["test_title"])
    print(errors[:800])
    assert "Name is required" in errors or "form-errors" in errors or "form_errors" in errors
