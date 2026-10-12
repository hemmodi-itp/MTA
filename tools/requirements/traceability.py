"""
traceability.py — test_creation/traceability.json: AC ↔ test case ↔ spec/title ↔ latest result (Phase 1.2).

Pure core (no I/O):
  build(...)            deterministic rebuild from requirements + scenarios + plans + suite (+ test data)
  apply_results(...)    fold one Playwright run's per-test results into the document
  uncovered_reason(...) why an AC has no test (first matching rule of design §5.3)
  summarise(...)        coverage numbers for the report and the benchmark

I/O wrappers (no-ops unless `requirements.enabled` and requirements.json exists):
  refresh_project(safe_project)                      after generation / before reporting
  apply_results_for_project(safe_project, results)   after every Playwright run
"""

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from tools.requirements.models import (
    AUTOMATABLE,
    LatestResult,
    RequirementsDoc,
    TraceAC,
    TraceabilityDoc,
    TraceTest,
    UncoveredReason,
)

# Plan-recorded drop reasons, in the order they are reported (design §5.3, rule 6).
_PLAN_DROP_REASONS = ("dropped_for_safety", "missing_locator", "missing_action",
                      "placeholder_negative_dropped", "locator_type_mismatch")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_path(p: Optional[str]) -> str:
    return (p or "").replace("\\", "/").lstrip("./")


def _priority_rank(p: Optional[str]) -> int:
    return int(p[1]) if p and len(p) == 2 and p[1].isdigit() else 9


# ── build ────────────────────────────────────────────────────────────────────

def _plan_tests(plans: Dict[str, Any]) -> Iterable[Tuple[str, int, dict]]:
    for sid, plan in (plans or {}).items():
        if not isinstance(plan, dict):
            continue
        for i, t in enumerate(plan.get("tests") or []):
            if isinstance(t, dict):
                yield sid, i, t


def _legacy_title(test: dict) -> str:
    from tools.test_creation.script_generator.spec_renderer import render_test_title
    return render_test_title(test)


def build(doc: RequirementsDoc, scenarios: List[dict], plans: Dict[str, Any], suite_specs: List[dict],
          test_data: Optional[List[dict]] = None, previous: Optional[TraceabilityDoc] = None,
          no_url_modules: Iterable[str] = (), project: Optional[str] = None,
          design_doc: Optional[dict] = None) -> TraceabilityDoc:
    from tools.requirements.linking import criteria_index, link_scenario, link_test

    # A scenario linked before the criteria it exercises existed (another module's, extracted later) gets a
    # project-wide, in-memory re-link here, so its tests are traced without regeneration.
    scenarios = [link_scenario(s, doc) if isinstance(s, dict) and not s.get("ac_ids") else s for s in scenarios]
    index = criteria_index(doc)
    scen_by_id = {s.get("scenario_id"): s for s in scenarios if isinstance(s, dict) and s.get("scenario_id")}
    spec_by_sid = {s.get("spec_id"): s for s in suite_specs if isinstance(s, dict) and s.get("spec_id")}
    prev_tests = previous.tests if previous else {}

    tests: Dict[str, TraceTest] = {}
    for sid, i, t in _plan_tests(plans):
        spec = spec_by_sid.get(sid)
        if not spec or not spec.get("file"):
            continue     # the plan was never rendered (all tests dropped, or generation failed)
        scenario = scen_by_id.get(sid, {})
        tc_id = t.get("tc_id") or f"{sid}#{i + 1}"
        if t.get("tc_id"):
            ac_ids, link = list(t.get("ac_ids") or []), t.get("ac_link") or ("direct" if t.get("ac_ids") else "")
            if not ac_ids and scenario.get("ac_ids"):
                # generated while its scenario had no links; its spec's tags catch up on regeneration
                ac_ids, link = link_test(t, scenario["ac_ids"], index)
        else:   # a spec generated before Phase 1: traced through its scenario
            ac_ids, link = list(scenario.get("ac_ids") or []), "legacy"
        prev = prev_tests.get(tc_id)
        tests[tc_id] = TraceTest(
            scenario_id=sid, module_id=spec.get("module_id") or scenario.get("module_id"),
            spec_file=spec.get("file"), test_title=t.get("title") or _legacy_title(t), type=t.get("type"),
            ac_ids=ac_ids, link=link if link in ("direct", "similarity", "inherited", "legacy") else "direct",
            latest_result=prev.latest_result if prev else LatestResult(),
            defect_ids=list(prev.defect_ids) if prev else [])

    acs = _build_acs(doc, scenarios, plans, spec_by_sid, test_data or [], tests, set(no_url_modules),
                     design_reasons(design_doc, plans))
    out = TraceabilityDoc(project=project or (previous.project if previous else doc.project), updated_at=_now(),
                          acs=acs, tests=tests,
                          unlinked_tests=sorted(k for k, v in tests.items() if not v.ac_ids))
    out.summary = summarise(out)
    return out


def design_reasons(design_doc: Optional[dict], plans: Dict[str, Any]) -> Dict[str, UncoveredReason]:
    """Phase 3: why a criterion's designed cases produced no test — a selected case the plan could not express
    (or whose generation failed), or every case for it cut by the budget in test_cases.json."""
    if not design_doc:
        return {}
    selected = design_doc.get("test_cases") or []
    selected_acs = {a for c in selected for a in c.get("ac_ids") or []}
    drops: Dict[str, str] = {}
    for plan in (plans or {}).values():
        for d in (plan or {}).get("dropped_tests") or [] if isinstance(plan, dict) else []:
            if isinstance(d, dict) and d.get("case_id"):
                drops.setdefault(d["case_id"], d.get("reason") or "not_expressed")
    out: Dict[str, UncoveredReason] = {}
    for c in selected:
        reason = drops.get(c.get("id"))
        if reason:
            for a in c.get("ac_ids") or []:
                out.setdefault(a, UncoveredReason(code=reason, detail=f"design case {c['id']}: {c.get('title', '')[:100]}"))
    for c in design_doc.get("cut") or []:
        for a in c.get("ac_ids") or []:
            if a not in selected_acs:
                out.setdefault(a, UncoveredReason(code=c.get("reason") or "budget",
                                                  detail=f"test design cut {c['id']} ({c.get('detail') or c.get('reason')})"))
    return out


def _build_acs(doc: RequirementsDoc, scenarios: List[dict], plans: Dict[str, Any], spec_by_sid: Dict[str, dict],
               test_data: List[dict], tests: Dict[str, TraceTest], no_url_modules: set,
               design: Optional[Dict[str, UncoveredReason]] = None) -> Dict[str, TraceAC]:
    req_of = doc.requirement_of()
    tc_by_ac: Dict[str, List[str]] = {}
    for tc_id, t in tests.items():
        for a in t.ac_ids:
            tc_by_ac.setdefault(a, []).append(tc_id)
    scen_by_ac: Dict[str, List[dict]] = {}
    for s in scenarios:
        for a in (s.get("ac_ids") or []) if isinstance(s, dict) else []:
            scen_by_ac.setdefault(a, []).append(s)
    capped = {d.get("scenario_id"): d.get("capped_variants") or {} for d in test_data if isinstance(d, dict)}
    generated_modules = {s.get("module_id") for s in spec_by_sid.values() if s.get("file")}

    acs: Dict[str, TraceAC] = {}
    reasons = {ac.id: ac.testability_reason for ac in doc.criteria()}
    for ac in doc.criteria():
        req = req_of[ac.id]
        entry = TraceAC(req_id=req.id, module_id=req.module_id, statement=ac.statement, priority=ac.priority,
                        testability=ac.testability, risk_tags=list(ac.risk_tags), parent_id=ac.parent_id,
                        children=list(ac.children), tc_ids=sorted(set(tc_by_ac.get(ac.id, []))))
        acs[ac.id] = entry
    for ac_id, entry in acs.items():
        if entry.children:
            child_tcs = sorted({tc for c in entry.children for tc in acs[c].tc_ids if c in acs})
            entry.tc_ids = sorted(set(entry.tc_ids) | set(child_tcs))
            covered = [c for c in entry.children if c in acs and acs[c].tc_ids]
            entry.status = ("covered" if len(covered) == len(entry.children) else
                            "partial" if covered else "not_covered")
            if entry.status != "covered":
                missing = [c for c in entry.children if c not in covered]
                entry.uncovered_reason = UncoveredReason(code="children_uncovered",
                                                         detail=", ".join(missing))
        else:
            entry.status = "covered" if entry.tc_ids else "not_covered"
            if not entry.tc_ids:
                entry.uncovered_reason = uncovered_reason(
                    entry, scen_by_ac.get(ac_id, []), plans, spec_by_sid, capped, generated_modules,
                    no_url_modules, reasons.get(ac_id, ""), (design or {}).get(ac_id))
        entry.result = _aggregate_result([tests[t].latest_result.status for t in entry.tc_ids if t in tests])
    return acs


def uncovered_reason(entry: TraceAC, linked_scenarios: List[dict], plans: Dict[str, Any],
                     spec_by_sid: Dict[str, dict], capped: Dict[str, dict], generated_modules: set,
                     no_url_modules: set, testability_reason: str = "",
                     design_reason: Optional[UncoveredReason] = None) -> UncoveredReason:
    t = entry.testability
    if t in ("manual_only", "not_testable"):
        return UncoveredReason(code=t, detail=testability_reason)
    if t == "api":
        return UncoveredReason(code="not_supported:api", detail="MTA does not generate API tests yet (Phase 8)")
    if t == "non_functional":
        return UncoveredReason(code="not_supported:non_functional",
                               detail="MTA does not generate non-functional tests yet (Phase 7)")
    if entry.module_id and entry.module_id in no_url_modules:
        return UncoveredReason(code="no_url", detail="BRD-only discovery: no URL, so no locators")
    if design_reason is not None:
        return design_reason
    if entry.module_id and entry.module_id not in generated_modules:
        return UncoveredReason(code="module_not_generated",
                               detail=f"no spec has been generated for module {entry.module_id} yet")
    if not linked_scenarios:
        return UncoveredReason(code="no_scenario", detail="no business scenario covers this criterion")
    sids = [s.get("scenario_id") for s in linked_scenarios]
    for reason in _PLAN_DROP_REASONS:
        hits = [sid for sid in sids if _plan_has(plans.get(sid), reason)]
        if hits:
            return UncoveredReason(code=reason, detail=f"scenario(s) {', '.join(hits)}")
    budget = [sid for sid in sids if sum((capped.get(sid) or {}).values()) > 0]
    if budget:
        return UncoveredReason(code="budget", detail=f"test_generation caps removed variants for {', '.join(budget)}")
    failed = [sid for sid in sids if not (spec_by_sid.get(sid) or {}).get("file")]
    if failed:
        return UncoveredReason(code="generation_failed", detail=f"no spec for scenario(s) {', '.join(failed)}")
    return UncoveredReason(code="no_test_targets_ac",
                           detail=f"scenario(s) {', '.join(sids)} have tests, none linked to this criterion")


def _plan_has(plan: Optional[dict], reason: str) -> bool:
    if not isinstance(plan, dict):
        return False
    if reason == "dropped_for_safety":
        return bool(plan.get("dropped_for_safety"))
    if reason == "missing_locator":
        return bool(plan.get("missing_locators"))
    if reason == "missing_action":
        return bool(plan.get("missing_actions"))
    return any(isinstance(d, dict) and d.get("reason") == reason for d in plan.get("dropped_tests") or [])


def _aggregate_result(statuses: List[str]) -> str:
    s = set(statuses)
    if not s or s == {"not_run"}:
        return "not_run"
    if s == {"passed"}:
        return "passed"
    if "failed" in s:
        return "mixed" if ("passed" in s or "flaky" in s) else "failed"
    if "flaky" in s:            # Phase 4.7: an AC whose only non-pass is a flaky test is flaky, not passing
        return "flaky"
    if s <= {"skipped", "not_run"}:
        return "skipped"
    return "mixed"


# ── results ──────────────────────────────────────────────────────────────────

def result_status(r: dict) -> str:
    """passed | flaky | failed | skipped. Phase 4.7: a test that failed and then passed on a retry is "flaky",
    never "passed"."""
    pw = str(r.get("pw_status") or "").lower()
    if pw in ("expected", "passed"):
        return "passed"
    if pw == "flaky":
        return "flaky"
    if pw == "skipped":
        return "skipped"
    if pw in ("unexpected", "failed", "timedout", "interrupted"):
        return "failed"
    st = str(r.get("status") or "").lower()
    return {"success": "passed", "passed": "passed", "flaky": "flaky", "skipped": "skipped"}.get(st, "failed")


def _first_error(r: dict) -> Optional[str]:
    for e in r.get("errors") or []:
        line = _ANSI.sub("", str(e or "")).strip().splitlines()
        if line:
            return line[0][:300]
    return None


def _match(trace: TraceabilityDoc, r: dict) -> Optional[str]:
    tc = r.get("tc_id")
    if tc and tc in trace.tests:
        return tc
    spec, title = _norm_path(r.get("spec_file")), (r.get("test_title") or "").strip()
    for tc_id, t in trace.tests.items():
        if t.spec_file and spec.endswith(_norm_path(t.spec_file)) and (t.test_title or "").strip() == title:
            return tc_id
    return None


def apply_results(trace: TraceabilityDoc, results: List[dict], run: Optional[str] = None,
                  at: Optional[str] = None) -> Tuple[TraceabilityDoc, int]:
    """Update latest_result for every matched test; returns (doc, unmatched result count)."""
    unmatched = 0
    at = at or _now()
    for r in results or []:
        tc_id = _match(trace, r)
        if tc_id is None:
            unmatched += 1
            continue
        status = result_status(r)
        trace.tests[tc_id].latest_result = LatestResult(
            status=status, pw_status=r.get("pw_status"), run=run, at=at,
            last_failure=_first_error(r) if status == "failed" else None)
    for entry in trace.acs.values():
        entry.result = _aggregate_result([trace.tests[t].latest_result.status for t in entry.tc_ids
                                          if t in trace.tests])
    trace.updated_at = at
    trace.summary = summarise(trace, unmatched_results=unmatched)
    return trace, unmatched


# ── summary ──────────────────────────────────────────────────────────────────

def summarise(trace: TraceabilityDoc, unmatched_results: Optional[int] = None) -> Dict[str, Any]:
    leaves = {k: v for k, v in trace.acs.items() if not v.children}
    automatable = {k: v for k, v in leaves.items() if v.testability in AUTOMATABLE}
    covered = [k for k, v in automatable.items() if v.status == "covered"]
    by_reason: Dict[str, int] = {}
    for v in leaves.values():
        if v.uncovered_reason:
            by_reason[v.uncovered_reason.code] = by_reason.get(v.uncovered_reason.code, 0) + 1
    links: Dict[str, int] = {}
    results: Dict[str, int] = {}
    for t in trace.tests.values():
        links[t.link if t.ac_ids else "unlinked"] = links.get(t.link if t.ac_ids else "unlinked", 0) + 1
        results[t.latest_result.status] = results.get(t.latest_result.status, 0) + 1
    out = {
        "acs_total": len(leaves),
        "acs_automatable": len(automatable),
        "acs_covered": len(covered),
        "coverage_pct": round(100.0 * len(covered) / len(automatable), 1) if automatable else None,
        "acs_covered_any": sum(1 for v in leaves.values() if v.status == "covered"),
        "acs_passing": sum(1 for v in leaves.values() if v.result == "passed"),
        "acs_flaky": sum(1 for v in leaves.values() if v.result == "flaky"),
        "acs_failing": sum(1 for v in leaves.values() if v.result in ("failed", "mixed")),
        "non_atomic_parents": sum(1 for v in trace.acs.values() if v.children),
        "by_reason": dict(sorted(by_reason.items())),
        "tests_total": len(trace.tests),
        "tests_unlinked": len(trace.unlinked_tests),
        "test_links": dict(sorted(links.items())),
        "test_results": dict(sorted(results.items())),
    }
    if unmatched_results is not None:
        out["unmatched_results"] = unmatched_results
    return out


# ── report section ───────────────────────────────────────────────────────────

def _id_key(ac_id: str) -> Tuple:
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"[-.]", ac_id))


def report_section(trace: TraceabilityDoc) -> Dict[str, Any]:
    """The traceability block of the JSON/HTML report: every AC with its tests and latest result, the ACs with
    zero tests and why, and the tests linked to no AC."""
    acs = []
    for ac_id in sorted(trace.acs, key=_id_key):
        a = trace.acs[ac_id]
        acs.append({
            "id": ac_id, "req_id": a.req_id, "module_id": a.module_id, "statement": a.statement,
            "priority": a.priority, "testability": a.testability, "risk_tags": a.risk_tags,
            "parent_id": a.parent_id, "children": a.children, "status": a.status, "result": a.result,
            "uncovered_reason": a.uncovered_reason.model_dump() if a.uncovered_reason else None,
            "tests": [{"tc_id": t, "title": trace.tests[t].test_title, "spec_file": trace.tests[t].spec_file,
                       "link": trace.tests[t].link, "status": trace.tests[t].latest_result.status}
                      for t in a.tc_ids if t in trace.tests],
        })
    uncovered = [{"id": a["id"], "module_id": a["module_id"], "priority": a["priority"],
                  "testability": a["testability"], **(a["uncovered_reason"] or {})}
                 for a in acs if not a["children"] and a["status"] != "covered"]
    unlinked = [{"tc_id": k, "title": trace.tests[k].test_title, "spec_file": trace.tests[k].spec_file}
                for k in trace.unlinked_tests if k in trace.tests]
    return {"summary": trace.summary, "acs": acs, "uncovered": uncovered, "unlinked_tests": unlinked}


# ── I/O wrappers ─────────────────────────────────────────────────────────────

def traceability_path(safe_project: str) -> str:
    from contracts.artifacts.paths import artifact_path
    from tools.requirements.config import project_dir
    return artifact_path(project_dir(safe_project), "traceability")


def load_traceability(safe_project: str) -> Optional[TraceabilityDoc]:
    from contracts.artifacts.io import load_payload
    path = traceability_path(safe_project)
    if not os.path.exists(path):
        return None
    return TraceabilityDoc.model_validate(load_payload("traceability", path))


def save_traceability(safe_project: str, trace: TraceabilityDoc) -> str:
    from contracts.artifacts.io import save_artifact
    path = traceability_path(safe_project)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return save_artifact("traceability", path, trace.model_dump(mode="json"))


def _no_url_modules(safe_project: str, doc: RequirementsDoc) -> List[str]:
    """Modules with no URL anywhere (project.url or modules[].url) ran BRD-only discovery."""
    import yaml

    from tools.requirements.config import project_dir
    try:
        with open(os.path.join(project_dir(safe_project), "project.yaml"), encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return []
    if (raw.get("project") or {}).get("url"):
        return []
    urls = {m.get("id"): m.get("url") for m in raw.get("modules") or [] if isinstance(m, dict)}
    return [r.module_id for r in doc.requirements if r.module_id and not urls.get(r.module_id)]


def refresh_project(safe_project: str, request: Optional[dict] = None) -> Optional[TraceabilityDoc]:
    """Rebuild traceability.json from the project's artifacts. None when the feature is off / not set up."""
    from contracts.artifacts.io import load_payload, load_records
    from contracts.artifacts.paths import artifact_path
    from tools.requirements.config import project_dir, requirements_enabled
    from tools.requirements.store import load_requirements

    if not requirements_enabled(safe_project, request):
        return None
    doc = load_requirements(safe_project)
    if doc is None:
        return None
    pdir = project_dir(safe_project)

    def _load(name: str, default: Any) -> Any:
        path = artifact_path(pdir, name, existing_only=True)
        return load_payload(name, path, default) if path else default

    scenarios = (_load("business_scenarios", {}) or {}).get("scenarios") or []
    plans = _load("test_plans", {}) or {}
    suite = (_load("test_suite", {}) or {}).get("specs") or []
    td_path = artifact_path(pdir, "test_data", existing_only=True)
    test_data = load_records(td_path) if td_path else []
    previous = load_traceability(safe_project)
    from tools.test_design.config import design_enabled

    # Phase 3 reasons only with a profile: a test_cases.json left behind must not change legacy output
    tc_path = artifact_path(pdir, "test_cases", existing_only=True) if design_enabled(safe_project, request) else None
    design_doc = load_payload("test_cases", tc_path, None) if tc_path else None
    trace = build(doc, scenarios, plans, suite, test_data, previous,
                  no_url_modules=_no_url_modules(safe_project, doc), project=safe_project,
                  design_doc=design_doc)
    save_traceability(safe_project, trace)
    return trace


def apply_results_for_project(safe_project: str, results: List[dict], run: Optional[str] = None,
                              request: Optional[dict] = None) -> Optional[TraceabilityDoc]:
    from tools.requirements.config import requirements_enabled

    if not requirements_enabled(safe_project, request):
        return None
    trace = load_traceability(safe_project) or refresh_project(safe_project, request)
    if trace is None:
        return None
    trace, _ = apply_results(trace, results, run=run)
    save_traceability(safe_project, trace)
    return trace
