"""Phase 4.5 migration — rerender.py rebuilds specs from test_plans.json through compose_spec (no LLM)."""

import json
import os

from tools.test_creation.script_generator.compose import compose_spec
from tools.test_creation.script_generator.rerender import main, rerender_project

PLAN = {"tests": [{"name": "valid save", "type": "positive", "steps": [
    {"action": "navigate"}, {"action": "click", "locator_key": "save"}]}]}
SETUP = [{"goto": "http://127.0.0.1:1/login"}, {"click": "#go"}, {"wait": 500}]


def _project(base, execution="", role_line=""):
    pdir = os.path.join(base, "shop")
    tc = os.path.join(pdir, "test_creation")
    os.makedirs(os.path.join(tc, "test_scripts", "M03"))
    os.makedirs(os.path.join(pdir, "test_comprehension"))
    with open(os.path.join(pdir, "project.yaml"), "w", encoding="utf-8") as fh:
        fh.write(f"""project: {{name: shop}}
auth:
  roles:
    user: {{strategy: setup}}
modules:
  - id: M03
    url: http://127.0.0.1:1/products/new
{role_line}    setup:
      - goto: http://127.0.0.1:1/login
      - click: "#go"
      - wait: 500
{execution}""")
    json.dump({"scenarios": [{"scenario_id": "M03_BS_001", "title": "Create"}]},
              open(os.path.join(pdir, "test_comprehension", "business_scenarios.json"), "w"))
    json.dump({"schema_version": 2, "artifact": "test_plans", "plans": {"M03_BS_001": PLAN}},
              open(os.path.join(tc, "test_plans.json"), "w"))
    rel = "M03/test_M03_BS_001_create.spec.ts"
    json.dump({"specs": [
        {"spec_id": "M03_BS_001", "module_id": "M03", "file": rel, "generation_mode": "action_library"},
        {"spec_id": "M03_BS_009", "module_id": "M03", "file": "M03/legacy.spec.ts", "generation_mode": None},
    ]}, open(os.path.join(tc, "test_suite.json"), "w"))
    spec_path = os.path.join(tc, "test_scripts", rel)
    legacy = compose_spec(PLAN, {"scenario_id": "M03_BS_001", "title": "Create"}, "http://127.0.0.1:1/products/new",
                          os.path.join("projects", "shop", "test_creation", "test_scripts", rel),
                          project="shop", module_setup=SETUP)
    with open(spec_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(legacy)
    return spec_path


def test_same_options_give_zero_diff(tmp_path):
    spec = _project(str(tmp_path), execution="execution: {test_steps: false}\n")
    out = rerender_project("shop", check=True, projects_base=str(tmp_path), out=lambda s: None)
    assert out["changed"] == [] and out["unchanged"] == ["M03_BS_001"]
    assert out["skipped"] == [{"spec_id": "M03_BS_009", "reason": "no stored action-library plan"}]
    assert os.path.exists(spec)


def test_check_prints_the_diff_and_writes_nothing(tmp_path):
    spec = _project(str(tmp_path))                       # default: test_steps true
    before = open(spec, encoding="utf-8").read()
    diffs = []
    out = rerender_project("shop", check=True, projects_base=str(tmp_path), out=diffs.append)
    assert out["changed"] == ["M03_BS_001"]
    assert "+    await test.step(" in "".join(diffs)
    assert open(spec, encoding="utf-8").read() == before and not os.path.exists(spec + ".bak")


def test_write_mode_rerenders_and_keeps_a_backup(tmp_path):
    spec = _project(str(tmp_path))
    rerender_project("shop", projects_base=str(tmp_path))
    text = open(spec, encoding="utf-8").read()
    assert text.count("await test.step(") == 2 and "waitForLoadState('load')" in text
    assert os.path.exists(spec + ".bak")


def test_module_roles_render_test_use_role(tmp_path):
    spec = _project(str(tmp_path), execution="execution: {module_roles: true, role_auth: true}\n",
                    role_line="    role: user\n")
    rerender_project("shop", projects_base=str(tmp_path))
    text = open(spec, encoding="utf-8").read()
    assert 'test.use({ role: "user" });' in text and "beforeEach" not in text


def test_cli_exit_codes(tmp_path, monkeypatch):
    import tools.constants as constants
    _project(str(tmp_path))
    monkeypatch.setattr(constants, "PROJECTS_BASE", str(tmp_path))
    assert main(["--project", "shop", "--check"]) == 1          # would change
    assert main(["--project", "shop"]) == 0
    assert main(["--project", "shop", "--check"]) == 0          # now clean
    assert main(["--project", "nope"]) == 2
