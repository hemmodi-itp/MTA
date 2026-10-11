"""Phase 2 integration points without a browser: contracts, project.yaml wiring, the deep-discovery
service (reuse / skip / failure), DiscoveryAgent + orchestrator hooks, the benchmark ground truth and
the discovery metrics scorer."""

import datetime as _dt
import json
import os
import re
import time

import pytest
import yaml

from contracts.artifacts import save_artifact
from contracts.artifacts.boundary import STEP_ARTIFACTS
from contracts.artifacts.io import validate_document
from contracts.artifacts.models import DomElementsV2, LocatorEntry
from contracts.artifacts.paths import artifact_path
from contracts.artifacts.registry import ARTIFACTS

NEW = ("app_map", "form_model", "api_inventory", "permission_matrix", "baseline")
NOW = "2026-10-11T00:00:00Z"


def _docs():
    return {
        "app_map": {"project": "p", "generated_at": NOW, "config_hash": "h", "states": [
            {"state_id": "S-1", "url": "http://h/", "url_template": "/", "structural_hash": "x", "roles": ["default"],
             "elements": [{"locator_id": "S-1:E-001", "anything": {"goes": True}}]}],
            "transitions": [{"from_state": "S-1", "action": "navigate", "element": {"name": "Home"}}]},
        "form_model": {"project": "p", "generated_at": NOW, "environment": "local", "probe_mode": "full",
                       "forms": [{"form_id": "F-1", "state_id": "S-1", "url": "http://h/", "url_template": "/", "role": "default",
                                  "fields": [{"name": "q"}], "probes": [{"probe": "empty"}]}]},
        "api_inventory": {"project": "p", "generated_at": NOW,
                          "endpoints": [{"method": "GET", "path_template": "/", "kind": "page"}]},
        "permission_matrix": {"project": "p", "generated_at": NOW, "roles": ["a"],
                              "states": [{"url_template": "/", "sample_url": "http://h/", "access": {"a": "reachable"}}]},
        "baseline": {"project": "p", "generated_at": NOW, "states": {"S-1": {"url": "http://h/", "role": "a"}}},
    }


# ── contracts ───────────────────────────────────────────────────────────

def test_new_artifacts_are_registered_and_validated_at_the_discovery_boundary():
    for name in NEW:
        assert ARTIFACTS[name].kind == "dict"
        assert name in STEP_ARTIFACTS["discovery"]


@pytest.mark.parametrize("name", NEW)
def test_new_artifacts_round_trip(tmp_path, name):
    path = str(tmp_path / f"{name}.json")
    save_artifact(name, path, _docs()[name])
    with open(path, encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["schema_version"] == 2 and on_disk["artifact"] == name
    assert validate_document(name, on_disk).ok


@pytest.mark.parametrize("name", NEW)
def test_new_artifacts_are_strict_at_the_top_level(name):
    doc = {**_docs()[name], "schema_version": 2, "artifact": name, "surprise": 1}
    assert not validate_document(name, doc).ok


def test_artifact_paths_resolve_in_both_comprehension_dirs(tmp_path):
    legacy = tmp_path / "comprehension"
    legacy.mkdir()
    (legacy / "app_map.json").write_text("{}")
    assert artifact_path(str(tmp_path), "app_map", existing_only=True).endswith(os.path.join("comprehension", "app_map.json"))
    assert artifact_path(str(tmp_path), "form_model").endswith(os.path.join("test_comprehension", "form_model.json"))


def test_existing_artifact_contracts_accept_the_new_optional_fields():
    DomElementsV2(elements=[{"locator_id": "LOC-0001", "constraints": {"maxlength": 5}, "frame": {"path": ["#f"]},
                             "capture_mode": "deep"}], scan={"mode": "deep"})
    entry = LocatorEntry(type="role", locator="button", name="Save", frame=["#f"],
                         scope={"type": "role", "locator": "dialog", "name": "Edit"})
    assert entry.scope.locator == "dialog"
    assert LocatorEntry(type="css", locator="#a").frame is None


# ── project.yaml wiring ─────────────────────────────────────────────────

def _project(base, name, extra):
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    raw = {"project": {"name": name, "url": "http://127.0.0.1:9/home"}, "environment": "local",
           "modules": [{"id": "M01", "url": "http://127.0.0.1:9/a", "setup": [{"goto": "http://127.0.0.1:9/login"}]},
                       {"id": "M02", "url": "http://127.0.0.1:9/b"}, {"id": "M03", "url": "http://127.0.0.1:9/a"}]}
    raw.update(extra)
    with open(os.path.join(d, "project.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(raw, f)
    return d


def test_manifest_carries_the_discovery_block_and_roles(_isolate_projects_base):
    from tools.project_manifest import load_project_manifest
    _project(_isolate_projects_base, "p1", {"discovery": {"deep": True, "max_pages": 7},
                                            "auth": {"enabled": False, "roles": {"guest": {"anonymous": True}}}})
    m = load_project_manifest("p1")
    assert m["discovery"]["deep"] is True and m["discovery"]["max_pages"] == 7
    assert m["auth_roles"] == [{**m["auth_roles"][0], "name": "guest", "strategy": "anonymous"}]
    assert "auth" not in m          # auth.enabled false keeps the single-identity auth off


def test_manifest_defaults_deep_discovery_off(_isolate_projects_base):
    from tools.project_manifest import load_project_manifest
    _project(_isolate_projects_base, "p2", {})
    m = load_project_manifest("p2")
    assert m["discovery"]["deep"] is False and "auth_roles" not in m


def test_project_template_and_benchmark_template_turn_deep_discovery_on():
    with open(os.path.join("application_assets", "projects", "aAprojectTemplate", "project.yaml"), encoding="utf-8") as f:
        assert (yaml.safe_load(f).get("discovery") or {}).get("deep") is True
    with open(os.path.join("benchmarks", "apps", "buggy_shop", "mta_project", "project.yaml.tmpl"), encoding="utf-8") as f:
        raw = yaml.safe_load(f.read().replace("{{BASE_URL}}", "http://h").replace("{{PROJECT_NAME}}", "b"))
    assert raw["discovery"]["deep"] is True
    assert sorted(raw["auth"]["roles"]) == ["admin", "guest", "user"] and raw["auth"]["enabled"] is False


# ── service ─────────────────────────────────────────────────────────────

def test_seeds_are_project_url_plus_unique_module_urls():
    from tools.discovery.deep.service import build_seeds
    seeds = build_seeds({"url": "http://h/", "modules": [{"id": "M1", "url": "http://h/a", "setup": [{"goto": "x"}]},
                                                       {"id": "M2", "url": "http://h/a"}, {"id": "M3"}, {"id": "M4", "url": "ftp:x"}]})
    assert [(s["url"], s["module_id"]) for s in seeds] == [("http://h/", None), ("http://h/a", "M1")]
    assert seeds[1]["setup_steps"] == [{"goto": "x"}]


def test_service_is_a_no_op_when_disabled_or_interactive(_isolate_projects_base):
    from tools.discovery.deep.service import ensure_app_discovery
    _project(_isolate_projects_base, "off", {})
    assert ensure_app_discovery("off")["status"] == "disabled"
    _project(_isolate_projects_base, "rec", {"discovery": {"deep": True}, "project": {"url": "http://h/", "interactive_scan": True}})
    assert ensure_app_discovery("rec")["status"] == "skipped"
    _project(_isolate_projects_base, "nourl", {"discovery": {"deep": True}, "project": {}, "modules": []})
    assert ensure_app_discovery("nourl")["status"] == "skipped"


def test_service_writes_artifacts_then_reuses_them(_isolate_projects_base, monkeypatch):
    from tools.discovery.deep import crawl, service
    _project(_isolate_projects_base, "p3", {"discovery": {"deep": True, "reuse_minutes": 60}})
    runs = []

    class FakeDiscovery:
        def __init__(self, project, cfg, roles, seeds, policy, **kw):
            runs.append((project, [r.name for r in roles], [s["url"] for s in seeds], kw.get("config_hash")))
            self.h = kw.get("config_hash")

        def run(self):
            docs = _docs()
            docs["app_map"]["config_hash"] = self.h
            docs["app_map"]["generated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
            return docs

    monkeypatch.setattr(crawl, "DeepDiscovery", FakeDiscovery)
    first = service.ensure_app_discovery("p3")
    assert first["status"] == "success" and first["states"] == 1 and first["forms"] == 1
    assert runs[0][1] == ["default"] and runs[0][2] == ["http://127.0.0.1:9/home", "http://127.0.0.1:9/a", "http://127.0.0.1:9/b"]
    for name in NEW:
        assert os.path.exists(first["paths"][name])
    assert service.ensure_app_discovery("p3")["status"] == "reused" and len(runs) == 1
    assert service.ensure_app_discovery("p3", force=True)["status"] == "success" and len(runs) == 2
    # a config change invalidates the reuse
    _project(_isolate_projects_base, "p3", {"discovery": {"deep": True, "reuse_minutes": 60, "max_pages": 3}})
    assert service.ensure_app_discovery("p3")["status"] == "success" and len(runs) == 3


def test_service_never_raises(_isolate_projects_base, monkeypatch):
    from tools.discovery.deep import crawl, service
    _project(_isolate_projects_base, "p4", {"discovery": {"deep": True}})

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("browser exploded")

    monkeypatch.setattr(crawl, "DeepDiscovery", Boom)
    out = service.ensure_app_discovery("p4")
    assert out["status"] == "failed" and "browser exploded" in out["error"]


def test_discovery_overrides(_isolate_projects_base, monkeypatch):
    from tools.discovery.deep import crawl, service
    _project(_isolate_projects_base, "p5", {})
    seen = {}

    class Capture:
        def __init__(self, project, cfg, *a, **k):
            seen["cfg"] = cfg

        def run(self):
            return _docs()

    monkeypatch.setattr(crawl, "DeepDiscovery", Capture)
    out = service.ensure_app_discovery("p5", discovery_overrides={"deep": True, "validation": {"enabled": False}})
    assert out["status"] == "success" and seen["cfg"].validation.enabled is False
    assert seen["cfg"].validation.max_probes_per_form == 20


# ── DiscoveryAgent + orchestrator hooks ─────────────────────────────────

def _agent_request(base, deep):
    return {"project_name": "p6", "url": "http://127.0.0.1:9/a", "safety": {"allowed_hosts": ["127.0.0.1"]},
            "discovery": {"deep": deep, "max_pages": 3}}


def test_discovery_agent_keeps_the_legacy_scan_when_deep_is_off(monkeypatch):
    import agents.comprehension.discovery.agent as A
    calls = {}
    monkeypatch.setattr(A, "scan_dom", lambda **kw: calls.setdefault("scan", kw) and {"elements": [], "element_count": 0})
    monkeypatch.setattr(A, "save_dom_scan", lambda **kw: {"dom_elements": "x", "dom_intents": "y"})
    monkeypatch.setattr(A, "ensure_app_discovery", lambda *a, **k: calls.setdefault("deep", True))
    out = A.DiscoveryAgent()._run_dom_scan(_agent_request(None, False), "p6")
    assert calls["scan"]["deep_config"] is None and calls["scan"]["url_allowed"] is None
    assert "deep" not in calls and "deep_discovery" not in out


def test_discovery_agent_runs_the_deep_pass_when_on(monkeypatch):
    import agents.comprehension.discovery.agent as A
    calls = {}

    def fake_scan(**kw):
        calls["scan"] = kw
        return {"elements": [], "element_count": 0, "scan": {"mode": "deep"}}

    monkeypatch.setattr(A, "scan_dom", fake_scan)
    monkeypatch.setattr(A, "save_dom_scan", lambda **kw: {"dom_elements": "x", "dom_intents": "y"})
    monkeypatch.setattr(A, "ensure_app_discovery",
                        lambda name, request=None, force=False, log=None: calls.setdefault("deep", (name, force)) and {"status": "success"})
    req = {**_agent_request(None, True), "force_recrawl": True}
    out = A.DiscoveryAgent()._run_dom_scan(req, "p6")
    assert calls["scan"]["deep_config"]["deep"] is True
    assert calls["scan"]["url_allowed"]("http://127.0.0.1:9/x") and not calls["scan"]["url_allowed"]("http://evil.example/")
    assert calls["deep"] == ("p6", True) and out["deep_discovery"] == {"status": "success"}
    assert out["dom_scan_stats"] == {"mode": "deep"}


def test_a_failed_deep_pass_makes_discovery_partial_not_failed(monkeypatch):
    import agents.comprehension.discovery.agent as A
    agent = A.DiscoveryAgent()
    monkeypatch.setattr(agent, "_run_url_only", lambda request, state, safe: {
        "status": "success", "deep_discovery": {"status": "failed", "error": "boom"}})
    monkeypatch.setattr(agent, "_check_mandatory_outputs", lambda *a, **k: [])
    monkeypatch.setattr(agent, "_write_run_summary", lambda *a, **k: None)
    out = agent.execute({"project_name": "p6", "url": "http://h/"}, {})
    assert out["status"] == "partial" and out.get("blocking") is not True
    assert any("deep discovery failed: boom" in r for r in out["partial_reasons"])


def test_orchestrator_hints_when_cached_discovery_skips_the_crawl(_isolate_projects_base, caplog):
    import logging
    from agents.orchestrator.agent import OrchestratorAgent
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.logger = logging.getLogger("test.orch")
    with caplog.at_level(logging.WARNING, logger="test.orch"):
        orch._hint_missing_app_map("p7", {"discovery": {"deep": True}})
        orch._hint_missing_app_map("p7", {"discovery": {"deep": False}})
    msgs = [r.message for r in caplog.records]
    assert len(msgs) == 1 and "python -m tools.discovery.deep --project p7" in msgs[0]


def test_main_exposes_force_recrawl():
    with open("main.py", encoding="utf-8") as f:
        src = f.read()
    assert '"--force-recrawl"' in src and '"force_recrawl": args.force_recrawl' in src


# ── benchmark ground truth + scoring ────────────────────────────────────

def _truth(name):
    with open(os.path.join("benchmarks", "apps", "buggy_shop", name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_every_labelled_testid_exists_in_the_app_templates():
    with open(os.path.join("benchmarks", "apps", "buggy_shop", "templates.py"), encoding="utf-8") as f:
        templates = f.read()
    truth = _truth("elements.yaml")
    ids = {t for frame in truth["frames"].values() for t in frame}
    ids |= {e["testid"] for p in truth["pages"] for e in p.get("elements") or []}
    missing = sorted(t for t in ids if f'data-testid="{t}"' not in templates)
    assert missing == []
    assert {p["reachability"] for p in truth["pages"]} == {"link", "deep_link", "requires_state"}


def test_every_expected_message_is_a_real_app_message():
    src = ""
    for name in ("app.py", "templates.py"):
        with open(os.path.join("benchmarks", "apps", "buggy_shop", name), encoding="utf-8") as f:
            src += f.read()
    truth = _truth("validation_messages.yaml")
    texts = {e["text"] for form in truth["forms"] for e in form["expected"]}
    assert texts and all(t in src for t in texts), [t for t in texts if t not in src]


def _el(testid, **constraints):
    el = {"attribute_locators": {"testid": testid}}
    if constraints:
        el["constraints"] = constraints
    return el


def test_discovery_metrics_scoring():
    from tools.benchmark import discovery_metrics as D
    truth = {"frames": {"g": ["brand"]}, "pages": [
        {"template": "/login", "role": "guest", "reachability": "link", "frame": "g",
         "elements": [{"testid": "user", "constraints": {"type": "text", "required": True}}, {"testid": "go"}]},
        {"template": "/list", "role": "guest", "reachability": "link", "elements": [{"testid": "row", "count": 3}]},
        {"template": "/orders/{id}", "role": "guest", "reachability": "deep_link", "elements": [{"testid": "x"}]},
    ]}
    app_map = {"states": [
        {"url_template": "/login", "roles": ["guest"], "elements": [_el("brand"), _el("user", type="text", required=False), _el("go")]},
        {"url_template": "/list", "roles": ["guest"], "elements": [_el("row"), _el("row")]},
    ]}
    rec = D.element_recall(app_map, truth)
    assert rec["by_reachability"]["link"] == {"expected": 6, "found": 5} and rec["recall_link_pct"] == 83.3
    assert rec["recall_all_pct"] == round(100 * 5 / 7, 1)
    cc = D.constraint_capture(app_map, truth)
    assert (cc["checked"], cc["captured"]) == (2, 1) and cc["mismatches"][0]["constraint"] == "required"
    pc = D.page_coverage(app_map, truth)
    assert (pc["expected"], pc["covered"], pc["deep_link_only"]) == (2, 2, ["/orders/{id}"])
    form_model = {"forms": [{"url_template": "/login", "dom_id": "lf", "fields": [
        {"name": "user", "observed_messages": {"required_missing": {"text": "User is required"}}}],
        "probes": [{"probe": "too_long", "visible_errors": [{"text": "Invalid login"}]}]}]}
    msgs = {"forms": [{"template": "/login", "form": "lf", "expected": [
        {"field": "user", "probe": "required_missing", "text": "User is required"},
        {"field": None, "probe": "too_long", "text": "Invalid login"},
        {"field": "user", "probe": "too_long", "text": "Too long"}]},
        {"template": "/x", "form": "nope", "expected": [{"field": "a", "probe": "empty", "text": "t"}]}]}
    om = D.oracle_match(form_model, msgs)
    assert (om["expected"], om["matched"]) == (4, 2)
    assert {m["form_found"] for m in om["misses"]} == {True, False}
    md = D.render_md({"app": "a", "date": "d", "element_recall": rec, "constraint_capture": cc, "page_coverage": pc,
                      "oracle_match": om, "deep_discovery": {"duration_s": 1}})
    assert "Element recall (link-reachable) | 83.3%" in md and "## Unmatched messages" in md


def test_benchmark_reads_the_discovery_step_time(tmp_path, monkeypatch):
    from tools.benchmark import run as R
    monkeypatch.setattr(R, "REPO_ROOT", str(tmp_path))
    runs = tmp_path / "workflow_runs"
    runs.mkdir()
    since = time.time() - 1
    (runs / "20261011_000000_bench_x_abc.json").write_text(json.dumps(
        {"execution_trace": [{"step": "discovery", "duration_ms": 61234}, {"step": "testdata", "duration_ms": 5}]}))
    assert R._discovery_step_seconds("bench_x", since) == 61.2
    assert R._discovery_step_seconds("bench_y", since) is None


def test_scorer_and_report_carry_the_discovery_block():
    from tools.benchmark.report_md import render_markdown
    from tools.benchmark.score import _discovery_metrics
    m = _discovery_metrics({"status": "success", "seconds": 70.1, "states": 23, "forms": 10, "probes": 29, "endpoints": 14,
                            "paths": {"x": 1}, "metrics": {"element_recall_link_pct": 100.0, "oracle_match_pct": 100.0}})
    assert m["element_recall_link_pct"] == 100.0 and "paths" not in m
    assert _discovery_metrics(None) is None
    metrics = {"seeded_bug_detection": {"rate": 0.1, "caught": 1, "evaluated": 10, "enabled": 10, "by_category": {}, "bugs": []},
               "requirement_coverage": {"pct": 0.5, "covered": [], "total_acs": 2, "uncovered": []},
               "llm": {"cost_usd": None, "calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "unpriced_models": []},
               "heal_precision": {"precision": None, "applied": 0, "wrong": 0, "measured": False},
               "runtime_s": {"generation": 1, "total": 2, "discovery_by_module": {"M01": 60.5, "M02": None}},
               "false_failure": {"rate": 0, "failing_tests": []}, "flaky": {"rate": 0, "clean_runs": 1},
               "tests_executed": 1, "tests_total": 1, "app": "a", "discovery": m}
    md = render_markdown(metrics, {"date": "d"})
    assert "Deep discovery (Phase 2) | success in 70.1 s" in md and "M01 60.5, M02 n/a" in md
    assert "Element recall, link-reachable (vs elements.yaml) | 100.0%" in md
