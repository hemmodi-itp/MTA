"""Phase 12.3: contract tests — every deterministic agent's output validates against its schema, on recorded inputs.

Recorded inputs (tests/fixtures/recorded/buggy_shop/, copied from the bench_buggy_shop discovery run): requirements,
app_map, form_model, api_inventory and one Playwright JSON report with 3 failures. They run through, in a temporary
project under application_assets/projects/ (paths there are cwd-relative, as in production):

    TestDesignAgent (design_llm off) -> white-box extract.run + api_tests.generate -> TriageAgent (triage_llm and
    re-runs off) -> ReportingAgent

Each artifact a step writes is validated with contracts/artifacts (the same step -> artifact map the orchestrator
enforces: boundary.STEP_ARTIFACTS); artifacts without a registered model get a structural check. Each agent's returned
dict must contain the plain (undotted) output names its agent.json declares. Every agents/*/*/agent.json is checked
against the CLAUDE.md schema.
"""

import ast
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from contracts.artifacts.boundary import STEP_ARTIFACTS, validate_step_outputs
from contracts.artifacts.io import validate_file

ROOT = Path(__file__).resolve().parents[2]
REC = ROOT / "tests" / "fixtures" / "recorded" / "buggy_shop"
RECORDED = ("requirements", "business_scenarios", "app_map", "form_model", "api_inventory")
PROJECT = "selftest_contracts"          # no leading "_": _safe_name strips it
CATEGORIES = {"comprehension", "test_creation", "test_execution", "evaluation", "orchestrator"}

PROJECT_YAML = {
    "project": {"name": PROJECT, "application_name": "Buggy Shop", "browser": "chromium", "headless": True},
    "environment": "local",
    "base_url": "http://127.0.0.1:8765",
    "safety": {"allow_destructive": False, "allowed_hosts": ["127.0.0.1"]},
    "requirements": {"enabled": True},
    "test_generation": {"profile": "standard", "design_llm": False, "budget": {"max_tests": 400, "max_runtime_minutes": 45}},
    "white_box": {"enabled": True, "source_dir": "benchmarks/apps/buggy_shop"},
    "test_types": {"api": True},
    "auth": {"enabled": False, "roles": {"user": {"strategy": "setup"}, "admin": {"strategy": "setup"},
                                         "guest": {"anonymous": True}}},
    "healing": {"triage_llm": False, "flaky_rerun": False},
    "modules": [{"id": mid, "name": name, "url": f"http://127.0.0.1:8765{path}"} for mid, name, path in (
        ("M01", "Login", "/login"), ("M02", "Products", "/products"), ("M03", "Product Form", "/products/new"),
        ("M04", "Cart & Checkout", "/cart"), ("M05", "Upload", "/upload"), ("M06", "Admin", "/admin"))],
    "reporting": {"enhanced": True},
    "quality_gates": {"p0_pass_rate": 100},
}


def _agent_json(rel: str) -> dict:
    return json.loads((ROOT / "agents" / rel / "agent.json").read_text(encoding="utf-8"))


def _declared_outputs_present(rel: str, result: dict) -> None:
    """Every plain output name in agent.json is a key of the returned dict (dotted names are nested: a.b)."""
    missing = []
    for out in _agent_json(rel)["outputs"]:
        node = result
        for part in out["name"].split("."):
            if not isinstance(node, dict) or part not in node:
                missing.append(out["name"])
                break
            node = node[part]
    assert not missing, f"{rel}: agent.json declares outputs the agent does not return: {missing}"


def _assert_valid(reports) -> None:
    bad = [f"{r.artifact} ({r.path}): {r.errors[:3]}" for r in reports if not r.ok]
    assert not bad, "contract violations:\n" + "\n".join(bad)


@pytest.fixture(scope="module")
def _contract_base(tmp_path_factory):
    """One project for the whole pipeline (each step reads the one before), in a module-scoped tmp dir."""
    base = tmp_path_factory.mktemp("contracts") / "projects"
    pdir = base / PROJECT
    comp = pdir / "test_comprehension"
    comp.mkdir(parents=True)
    for name in RECORDED:
        shutil.copy(REC / f"{name}.json", comp / f"{name}.json")
    (pdir / "project.yaml").write_text(yaml.safe_dump(PROJECT_YAML, sort_keys=False), encoding="utf-8")
    (pdir / "test_creation").mkdir()
    return base


@pytest.fixture
def project(_contract_base, _isolate_projects_base, monkeypatch):
    """tests/conftest.py points every PROJECTS_BASE alias at a per-test dir; point those same aliases at the shared
    module dir instead (every binding the conftest set is found by its value)."""
    import sys
    import tools.constants
    import agents.test_creation.test_design.agent       # noqa: F401 — import before re-pointing their aliases
    import agents.test_execution.reporting.agent        # noqa: F401
    import agents.test_execution.triage.agent           # noqa: F401
    isolated, base = _isolate_projects_base, str(_contract_base)
    monkeypatch.setattr(tools.constants, "PROJECTS_BASE", base)
    for name, mod in list(sys.modules.items()):
        if mod is None or not name.startswith(("agents.", "tools.")):
            continue
        for attr in ("_ASSETS_BASE", "_PROJECTS_DIR", "PROJECTS_BASE"):
            if getattr(mod, attr, None) == isolated:
                monkeypatch.setattr(mod, attr, base)
    return _contract_base / PROJECT


# ── recorded inputs ──────────────────────────────────────────────────

@pytest.mark.parametrize("name", RECORDED)
def test_recorded_inputs_are_valid(name):
    _assert_valid([validate_file(name, str(REC / f"{name}.json"))])


def test_recorded_playwright_report_is_valid():
    _assert_valid([validate_file("playwright_report", str(REC / "playwright_report.json"))])


# ── the pipeline on recorded inputs ──────────────────────────────────

def test_test_design_outputs_validate(project):
    from agents.test_creation.test_design.agent import TestDesignAgent
    out = TestDesignAgent(settings={}).execute({"project_name": PROJECT}, {})
    assert out["status"] in ("success", "partial") and not out.get("skipped"), out
    assert out["llm"] in ("off", "disabled", None) or out["llm"] != "ok", out["llm"]      # design_llm: false
    _declared_outputs_present("test_creation/test_design", out)
    reports = validate_step_outputs(str(project), "test_design", out)
    assert "test_cases" in {r.artifact for r in reports}
    assert {r.artifact for r in reports} == {"test_cases"} | ({"locator_map"} if out["output"]["locator_keys_added"] else set())
    _assert_valid(reports)
    cases = json.loads(Path(out["output"]["test_cases"]).read_text(encoding="utf-8"))["test_cases"]
    assert out["summary"]["selected"] == len(cases) > 0 and out["summary"]["ac_coverage_pct"] > 50, out["summary"]
    reqs = json.loads((REC / "requirements.json").read_text(encoding="utf-8"))
    known = {ac["id"] for r in reqs["requirements"] for ac in r.get("acceptance_criteria", [])}
    cited = {a for c in cases for a in c.get("ac_ids") or []}
    assert cited and cited <= known, sorted(cited - known)[:5]      # DOM / app_map cases may cite no AC


def test_whitebox_rules_and_api_tests(project):
    from tools.whitebox import api_tests, extract
    doc = extract.run(project)
    assert doc is not None
    saved = json.loads((project / "test_comprehension" / "code_rules.json").read_text(encoding="utf-8"))
    # code_rules has no registered model: structural contract
    assert saved["artifact"] == "code_rules" and saved["schema_version"] == 1
    for key in ("routes", "rules", "functions", "contract"):
        assert key in saved, key
    assert saved["routes"] and all({"method", "path_template", "citation"} <= set(r) for r in saved["routes"])
    assert all(re.match(r".+:\d+$", r["citation"]) for r in saved["routes"] + saved["rules"] if r.get("citation"))
    files, summary = api_tests.generate(project)
    assert files and summary
    from tools.execution.selective import _spec_titles
    for f in files:
        text = Path(f).read_text(encoding="utf-8")
        titles = _spec_titles(text)
        assert titles and len(titles) == len(set(titles)), f"{f}: duplicate or missing test titles"


def test_triage_outputs(project):
    from agents.test_execution.triage.agent import TriageAgent
    rdir = project / "test_execution" / "reports" / "json"
    rdir.mkdir(parents=True, exist_ok=True)
    report = rdir / "20261011T125243Z_results.json"
    shutil.copy(REC / "playwright_report.json", report)
    out = TriageAgent(settings={}).execute({"project_name": PROJECT, "report_json": str(report),
                                            "triage_reruns": False}, {})
    assert out["status"] == "success", out
    _declared_outputs_present("test_execution/triage", out)
    _assert_valid(validate_step_outputs(str(project), "triage", out))     # [] today: triage writes reports
    tri = json.loads(Path(out["triage"]).read_text(encoding="utf-8"))
    assert len(tri["tests"]) == 3 and tri["refined"] is False
    from tools.triage import triage as tr
    verdicts = {tr.PRODUCT_DEFECT, tr.LOCATOR, tr.DATA, tr.ENVIRONMENT, tr.FLAKY, tr.KNOWN_ISSUE, tr.UNKNOWN}
    assert all(t["verdict"] in verdicts for t in tri["tests"]), [t["verdict"] for t in tri["tests"]]
    assert all(t.get("evidence") or t.get("reason") for t in tri["tests"])
    defects = json.loads(Path(out["defects"]).read_text(encoding="utf-8"))
    assert all(d["verdict"] == "product_defect" for d in defects)


def test_reporting_outputs_validate(project):
    from agents.test_execution.reporting.agent import ReportingAgent
    from tools.triage.service import statuses_from_report
    rep = json.loads((REC / "playwright_report.json").read_text(encoding="utf-8"))
    results = [{"spec_file": spec, "test_title": title, "status": "passed" if v["statuses"][-1] in ("passed", "expected")
                else "failed", "errors": []} for (spec, title), v in statuses_from_report(rep).items()]
    assert len(results) == 12
    state = {"run_id": "contracts", "workflow_name": "contracts", "outputs": {"ui_execution": {
        "status": "success", "passed": 9, "failed": 3, "results": results}}}
    out = ReportingAgent(settings={}).execute({"project_name": PROJECT, "run_id": "contracts"}, state)
    _declared_outputs_present("test_execution/reporting", out)
    _assert_valid(validate_step_outputs(str(project), "reporting", out))
    saved = json.loads(Path(out["report_path"]).read_text(encoding="utf-8"))
    for key in ("run_id", "project", "generated_at", "workflow_status", "test_execution_report", "quarantine", "quality"):
        assert key in saved, key
    assert Path(out["html_report_path"]).is_file() and Path(out["index_path"]).is_file()
    assert saved["quality"]["gates"]["verdict"] in ("PASS", "FAIL")


# ── every agent.json against the CLAUDE.md schema ────────────────────

AGENT_JSONS = sorted(ROOT.glob("agents/*/*/agent.json")) + [ROOT / "agents" / "orchestrator" / "agent.json"]
# registry hubs: agents/registry_setup.py (CLI workflows) and api/pipeline.py (the evaluation pipeline's steps)
REGISTRY_SETUP = "\n".join((ROOT / f).read_text(encoding="utf-8") for f in ("agents/registry_setup.py", "api/pipeline.py"))
FIELDS = {"name": str, "registry_key": (str, type(None)), "category": str, "module_path": str, "version": str,
          "status": str, "base_class": str, "llm_calls": bool, "description": str, "inputs": list, "outputs": list,
          "dependencies": list, "skills": list, "doc": str}


def _class_names() -> set:
    return {json.loads(p.read_text(encoding="utf-8")).get("name") for p in AGENT_JSONS}


def _skills_keys(skills_py: Path) -> set:
    tree = ast.parse(skills_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "SKILLS" for t in targets) and isinstance(node.value, ast.Dict):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError(f"{skills_py}: no literal SKILLS dict")


@pytest.mark.parametrize("path", AGENT_JSONS, ids=lambda p: p.parent.relative_to(ROOT / "agents").as_posix())
def test_agent_json_matches_the_schema(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    folder = path.parent
    errors = []
    for key, typ in FIELDS.items():
        if key not in d:
            errors.append(f"missing {key}")
        elif not isinstance(d[key], typ):
            errors.append(f"{key} is {type(d[key]).__name__}")
    if errors:
        pytest.fail(f"{path}: {errors}")
    rel = folder.relative_to(ROOT).as_posix()
    category_folder = folder.name if folder.parent.name == "agents" else folder.parent.name   # orchestrator is flat
    if d["category"] not in CATEGORIES or d["category"] != category_folder:
        errors.append(f"category {d['category']!r} vs folder {category_folder!r}")
    if d["module_path"] != rel.replace("/", ".") + ".agent":
        errors.append(f"module_path {d['module_path']!r} != {rel.replace('/', '.')}.agent")
    if d["status"] not in ("active", "stub"):
        errors.append(f"status {d['status']!r}")
    if d["base_class"] not in ("BaseAgent", "none"):
        errors.append(f"base_class {d['base_class']!r}")
    if d["doc"] != "agent.md" or not (folder / "agent.md").is_file():
        errors.append("doc must be agent.md and exist")
    if not d["description"].strip():
        errors.append("empty description")
    for i in d["inputs"]:
        if not ({"name", "type", "required", "description"} <= set(i)) or not isinstance(i["required"], bool):
            errors.append(f"input {i.get('name')!r} incomplete")
    for o in d["outputs"]:
        if not ({"name", "type", "description"} <= set(o)):
            errors.append(f"output {o.get('name')!r} incomplete")
    if d["registry_key"] is not None and not re.search(rf"[\"']{re.escape(d['registry_key'])}[\"']", REGISTRY_SETUP):
        errors.append(f"registry_key {d['registry_key']!r} not in registry_setup.py / api/pipeline.py")
    unknown = set(d["dependencies"]) - _class_names()
    if unknown:
        errors.append(f"unknown dependencies {sorted(unknown)}")
    if set(d["skills"]) != _skills_keys(folder / "skills.py"):
        errors.append(f"skills {sorted(d['skills'])} != skills.py SKILLS {sorted(_skills_keys(folder / 'skills.py'))}")
    if d["name"] not in (folder / "agent.py").read_text(encoding="utf-8"):
        errors.append(f"class {d['name']} not in agent.py")
    for f in ("__init__.py", "agent.py", "agent.md", "agent.json", "prompt.py", "server.py", "skills.py", "tools.py"):
        if not (folder / f).is_file():
            errors.append(f"missing {f}")
    assert not errors, f"{rel}: {errors}"
