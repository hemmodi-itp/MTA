"""Phase 11 (complete): the parts of the report summary.py does not cover. Pure Python, no I/O except history.

    severity_of        defect severity: test priority P0..P3 -> critical/high/medium/low (NFR: from the finding)
    defects_by_severity
    risk_areas         top N areas (module / requirement) by failures, untested high-priority ACs and flakiness
    record_history / trend   reports/history.json: one row per run; the summary shows the last 5 and the change
    coverage_dashboard requirement, technique, element, page/state, transition, API, role matrix, browser, test type —
                       and says plainly that code coverage is not measured
    nfr_counts         critical a11y / high security findings and the worst perf regression, read from the
                       findings JSON the NFR specs attach (not from counting failed tests)
    evidence           screenshot / trace / video / HAR / console attachments of a result, plus browser, role, run
    jira_issues / ado_work_items   defect exports (JSON a tracker's import or API accepts; nothing is posted)
    test_summary_report  ISO/IEC/IEEE 29119-3 style: scope, approach, deviations, coverage, results, defects,
                       residual risk, recommendation
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SEVERITY_BY_PRIORITY = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"}
SEVERITIES = ("critical", "high", "medium", "low")
_PRIORITY_WEIGHT = {"P0": 8, "P1": 4, "P2": 2, "P3": 1}
HISTORY_FILE = "history.json"
HISTORY_KEEP = 50


def _status(r: dict) -> str:
    return str(r.get("pw_status") or r.get("status") or "").lower()


def _failed(r: dict) -> bool:
    return _status(r) not in ("passed", "expected", "success", "skipped", "flaky")


def _plan_index(plans: dict) -> Dict[str, dict]:
    out = {}
    for plan in ((plans or {}).get("plans") or plans or {}).values():
        for t in (plan.get("tests") or []) if isinstance(plan, dict) else []:
            if isinstance(t, dict) and t.get("tc_id"):
                out[t["tc_id"]] = t
    return out


# ── severity ────────────────────────────────────────────────────────────────

def severity_of(result: dict, plan_test: Optional[dict] = None) -> str:
    tags = " ".join(result.get("tags") or []) + " " + str(result.get("test_title") or "")
    if "@a11y" in tags or "@security" in tags:
        return "high"
    prio = (plan_test or {}).get("priority")
    return SEVERITY_BY_PRIORITY.get(prio, "medium")


def defects_by_severity(defects: List[dict]) -> Dict[str, int]:
    out = {s: 0 for s in SEVERITIES}
    for d in defects:
        out[d.get("severity") or "medium"] = out.get(d.get("severity") or "medium", 0) + 1
    return out


# ── risk areas ──────────────────────────────────────────────────────────────

def _area(r: dict) -> str:
    sf = str(r.get("spec_file") or "").replace("\\", "/")
    m = re.search(r"test_scripts/([^/]+)/", sf)
    return m.group(1) if m else (sf.split("/")[0] if "/" in sf else "other")


def risk_areas(results: List[dict], trace: Optional[dict], plans: dict, top: int = 5) -> List[dict]:
    """Score per area: failed tests weighted by priority, untested P0/P1 ACs of the area's requirement, flaky tests."""
    idx = _plan_index(plans)
    areas: Dict[str, Dict[str, Any]] = {}

    def slot(name):
        return areas.setdefault(name, {"area": name, "score": 0, "failed": 0, "flaky": 0, "untested": 0, "why": []})
    for r in results:
        a = slot(_area(r))
        prio = (idx.get(r.get("tc_id") or "") or {}).get("priority") or "P2"
        if _failed(r):
            a["failed"] += 1
            a["score"] += _PRIORITY_WEIGHT.get(prio, 2)
        elif _status(r) == "flaky":
            a["flaky"] += 1
            a["score"] += 1
    for u in (trace or {}).get("uncovered") or []:
        if u.get("priority") in ("P0", "P1"):
            req = str(u.get("id") or "").rsplit(".", 1)[0] or "requirements"
            a = slot(f"requirement {req}")
            a["untested"] += 1
            a["score"] += _PRIORITY_WEIGHT[u["priority"]] // 2
    for a in areas.values():
        if a["failed"]:
            a["why"].append(f"{a['failed']} failing test(s)")
        if a["untested"]:
            a["why"].append(f"{a['untested']} untested P0/P1 criteria")
        if a["flaky"]:
            a["why"].append(f"{a['flaky']} flaky")
    ranked = sorted((a for a in areas.values() if a["score"]), key=lambda a: (-a["score"], a["area"]))
    return ranked[:top]


# ── history and trend ───────────────────────────────────────────────────────

def record_history(reports_dir: str, summary: dict, gates: Optional[dict], results: List[dict],
                   run: Optional[str] = None) -> List[dict]:
    """Append this run (idempotent per run id) to reports/history.json; returns the stored rows, oldest first."""
    path = os.path.join(reports_dir, HISTORY_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, ValueError):
        rows = []
    executed = [r for r in results if _status(r) != "skipped"]
    passed = sum(1 for r in executed if not _failed(r) and _status(r) != "flaky")
    row = {"run": run or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "at": datetime.now(timezone.utc).isoformat(),
           "pass_rate": round(100.0 * passed / len(executed), 1) if executed else None,
           "requirement_coverage": summary.get("requirement_coverage"),
           "product_defects": summary.get("product_defects"),
           "flaky": sum(1 for r in results if _status(r) == "flaky"),
           "tests": len(results), "verdict": (gates or {}).get("verdict")}
    rows = [x for x in rows if x.get("run") != row["run"]] + [row]
    rows = rows[-HISTORY_KEEP:]
    os.makedirs(reports_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)
    return rows


def trend(rows: List[dict], last: int = 5) -> Dict[str, Any]:
    """The last `last` runs before this one and the change of each metric against the previous run."""
    if not rows:
        return {"runs": [], "delta": {}}
    cur, prev = rows[-1], (rows[-2] if len(rows) > 1 else None)
    delta = {}
    for k in ("pass_rate", "requirement_coverage", "product_defects", "flaky"):
        if prev is not None and isinstance(cur.get(k), (int, float)) and isinstance(prev.get(k), (int, float)):
            delta[k] = round(cur[k] - prev[k], 1)
    return {"runs": rows[-(last + 1):-1], "delta": delta}


# ── coverage dashboard ──────────────────────────────────────────────────────

def _pct(n: int, d: int) -> Optional[float]:
    return round(100.0 * n / d, 1) if d else None


def coverage_dashboard(results: List[dict], trace: Optional[dict], plans: dict, test_cases: Optional[dict],
                       locator_map: Optional[dict], app_map: Optional[dict], api_inventory: Optional[dict],
                       spec_texts: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    ts = (trace or {}).get("summary") or {}
    cases = (test_cases or {}).get("test_cases") or []
    cut = (test_cases or {}).get("cut") or []
    by_tech: Dict[str, Dict[str, int]] = {}
    for c in cases:
        by_tech.setdefault(c.get("technique") or "other", {"selected": 0, "cut": 0})["selected"] += 1
    for c in cut:
        by_tech.setdefault(c.get("technique") or "other", {"selected": 0, "cut": 0})["cut"] += 1
    texts = " ".join((spec_texts or {}).values())
    keys = [k for k, e in (locator_map or {}).items() if isinstance(e, dict)]
    used = [k for k in keys if re.search(r"['\"]" + re.escape(k) + r"['\"]", texts)]
    templates = sorted({s.get("url_template") for s in (app_map or {}).get("states") or [] if s.get("url_template")})
    visited = [t for t in templates if t and _template_in(t, texts)]
    transitions = (app_map or {}).get("transitions") or []
    st_cases = [c for c in cases if c.get("technique") == "state_transition"]
    endpoints = [e for e in (api_inventory or {}).get("endpoints") or [] if e.get("kind") != "page"]
    hit_api = [e for e in endpoints if _template_in(e.get("path_template") or "", texts)]
    roles = {r for c in cases if c.get("technique") == "role_matrix" for r in c.get("roles") or []}
    browsers: Dict[str, int] = {}
    types: Dict[str, int] = {}
    idx = _plan_index(plans)
    for r in results:
        browsers[r.get("browser") or "default"] = browsers.get(r.get("browser") or "default", 0) + 1
        t = (idx.get(r.get("tc_id") or "") or {}).get("type") or _type_from_tags(r)
        types[t] = types.get(t, 0) + 1
    return {
        "requirement": {"covered": ts.get("acs_covered"), "total": ts.get("acs_automatable"),
                        "pct": ts.get("coverage_pct")},
        "technique": by_tech,
        "element": {"used": len(used), "total": len(keys), "pct": _pct(len(used), len(keys))},
        "page_state": {"tested": len(visited), "total": len(templates), "pct": _pct(len(visited), len(templates)),
                       "untested": [t for t in templates if t not in visited][:20]},
        "transition": {"cases": len(st_cases), "known": len(transitions)},
        "api": {"referenced": len(hit_api), "total": len(endpoints), "pct": _pct(len(hit_api), len(endpoints))},
        "role_matrix": {"roles": sorted(roles), "cases": sum(1 for c in cases if c.get("technique") == "role_matrix")},
        "browser": browsers,
        "test_type": types,
        "code": "not measured — needs the application to be instrumented (e.g. Istanbul / coverage.py on the server)",
    }


def _template_in(template: str, text: str) -> bool:
    """A url template like /products/{id} appears in spec text as /products/<something>."""
    if not template or not text:
        return False
    pat = re.escape(template.split("?")[0]).replace(r"\{id\}", r"[^\"'/?]+")
    pat = re.sub(r"\\\{[^}]+\\\}", r"[^\"'/?]+", pat)
    return re.search(r"[\"'`](?:https?://[^\"'`/]+)?" + pat + r"(?:[?\"'`/])", text) is not None


def _type_from_tags(r: dict) -> str:
    tags = " ".join(r.get("tags") or []) + " " + str(r.get("test_title") or "")
    for t in ("a11y", "visual", "perf", "security", "responsive", "resilience", "i18n"):
        if f"@{t}" in tags:
            return f"nfr:{t}"
    for t in ("positive", "negative", "boundary"):
        if f"@{t}" in tags:
            return t
    return "functional"


# ── NFR counts from the findings the specs attach ───────────────────────────

def _read_attachment(path: Optional[str]) -> Any:
    if not path:
        return None
    try:
        with open(path or "", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def nfr_counts(results: List[dict]) -> Dict[str, Any]:
    critical_a11y = high_security = 0
    worst_regression = None
    for r in results:
        for a in r.get("attachments") or []:
            name = str(a.get("name") or "")
            if name == "a11y-findings.json":
                for f in _read_attachment(a.get("path")) or []:
                    if f.get("level") == "fail" and str(f.get("rule", "")).startswith("axe:") and \
                            re.search(r"\((critical|serious)", str(f.get("message"))):
                        critical_a11y += 1
            elif name == "security-findings.json":
                high_security += sum(1 for f in _read_attachment(a.get("path")) or [] if f.get("level", "fail") == "fail")
        for ann in r.get("annotations") or []:
            m = re.search(r"is (\d+)% worse than the baseline", str(ann.get("description", "")))
            if m and str(ann.get("type", "")).startswith("perf"):
                worst_regression = max(worst_regression or 0, int(m.group(1)))
        if "@perf" in " ".join(r.get("tags") or []) + str(r.get("test_title")):
            for e in r.get("errors") or []:
                for m in re.finditer(r"is (\d+)% worse than the baseline", str(e)):
                    worst_regression = max(worst_regression or 0, int(m.group(1)))
    return {"critical_a11y": critical_a11y, "high_security": high_security, "perf_regression_pct": worst_regression}


# ── evidence and tracker exports ────────────────────────────────────────────

_KINDS = (("screenshot", ("screenshot", "image/png")), ("trace", ("trace",)), ("video", ("video",)),
          ("har", ("network.har",)), ("console", ("console-errors",)))


def evidence(result: dict, role: Optional[str] = None, run: Optional[str] = None, environment: str = "") -> Dict[str, Any]:
    atts = result.get("attachments") or []
    out: Dict[str, Any] = {}
    for kind, needles in _KINDS:
        hit = next((a.get("path") for a in atts if any(n in str(a.get("name", "")).lower()
                                                      or n in str(a.get("content_type", "")).lower() for n in needles)), None)
        if hit:
            out[kind] = hit
    if out.get("har"):
        har = _read_attachment(out["har"]) or {}
        bad = [f"{e['request']['method']} {e['request']['url']} -> {e['response']['status']}"
               for e in (har.get("log") or {}).get("entries") or []
               if (e.get("response") or {}).get("status", 0) >= 400][:5]
        if bad:
            out["har_excerpt"] = bad
    out.update({"browser": result.get("browser") or "", "role": role or _role_of(result), "run": run or "",
                "environment": environment})
    return out


def _role_of(result: dict) -> str:
    for a in result.get("annotations") or []:
        if a.get("type") == "role":
            return a.get("description", "")
    return ""


def jira_issues(defects: List[dict], project_key: str = "QA") -> List[dict]:
    """Jira REST v2 create-issue payloads (fields only — posting needs an explicit opt-in and credentials)."""
    prio = {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}
    out = []
    for d in defects:
        steps = "\n".join(f"# {s}" for s in d.get("steps") or [])
        ev = d.get("evidence") or {}
        desc = (f"h3. Steps to reproduce\n{steps}\n\nh3. Expected\n{d.get('expected')}\n\nh3. Actual\n{d.get('actual')}"
                f"\n\nh3. Evidence\n" + "\n".join(f"* {k}: {v}" for k, v in ev.items() if v))
        out.append({"fields": {"project": {"key": project_key}, "issuetype": {"name": "Bug"},
                               "summary": f"[MTA] {d.get('title')}"[:250], "description": desc,
                               "priority": {"name": prio.get(d.get("severity") or "medium", "Medium")},
                               "labels": ["mta"] + [a.replace(" ", "_") for a in d.get("ac_ids") or []]}})
    return out


def ado_work_items(defects: List[dict]) -> List[List[dict]]:
    """Azure DevOps JSON-Patch documents for `POST .../_apis/wit/workitems/$Bug` (nothing is posted)."""
    sev = {"critical": "1 - Critical", "high": "2 - High", "medium": "3 - Medium", "low": "4 - Low"}
    out = []
    for d in defects:
        repro = "<ol>" + "".join(f"<li>{s}</li>" for s in d.get("steps") or []) + "</ol>" + \
                f"<p><b>Expected:</b> {d.get('expected')}</p><p><b>Actual:</b> {d.get('actual')}</p>"
        out.append([
            {"op": "add", "path": "/fields/System.Title", "value": f"[MTA] {d.get('title')}"[:250]},
            {"op": "add", "path": "/fields/Microsoft.VSTS.TCM.ReproSteps", "value": repro},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Severity", "value": sev.get(d.get("severity") or "medium")},
            {"op": "add", "path": "/fields/System.Tags", "value": "; ".join(["mta"] + list(d.get("ac_ids") or []))},
        ])
    return out


# ── ISO/IEC/IEEE 29119-3 test summary report ────────────────────────────────

def test_summary_report(project: str, summary: dict, gates: dict, results: List[dict], defects: List[dict],
                        not_tested: List[dict], coverage: dict, risks: List[dict], deviations: List[str]) -> Dict[str, Any]:
    executed = [r for r in results if _status(r) != "skipped"]
    passed = sum(1 for r in executed if not _failed(r) and _status(r) != "flaky")
    verdict = (gates or {}).get("verdict", "NO_GATES")
    failed_gates = [g["gate"] for g in (gates or {}).get("gates") or [] if not g.get("ok")]
    high = [d for d in defects if d.get("severity") in ("critical", "high")]
    if verdict == "FAIL":
        rec = f"Do not release: quality gate(s) failed ({', '.join(failed_gates)})."
    elif high:
        rec = f"Release only after the {len(high)} critical/high defect(s) are fixed or accepted."
    elif not_tested:
        rec = f"Releasable with residual risk: {len(not_tested)} acceptance criteria are not tested."
    else:
        rec = "Releasable: gates passed and no critical/high defects."
    return {
        "scope": f"Project {project}: {len(results)} automated test(s) across "
                 f"{len({_area(r) for r in results})} area(s); {coverage.get('requirement', {}).get('total') or 0} "
                 "automatable acceptance criteria.",
        "approach": "Requirements-based test design (EP, BVA, decision table, state transition, role matrix, use "
                    "case), Playwright execution with outcome oracles, deterministic triage before any healing, "
                    "non-functional checks per project.yaml test_types.",
        "deviations": deviations or ["none recorded"],
        "coverage": {k: coverage.get(k) for k in ("requirement", "page_state", "element", "api")},
        "results": {"executed": len(executed), "passed": passed, "failed": sum(1 for r in executed if _failed(r)),
                    "flaky": sum(1 for r in results if _status(r) == "flaky"),
                    "skipped": len(results) - len(executed)},
        "defects": {"total": len(defects), "by_severity": defects_by_severity(defects)},
        "residual_risk": [f"{r['area']}: {', '.join(r['why'])}" for r in risks] +
                         ([f"{len(not_tested)} acceptance criteria not tested"] if not_tested else []),
        "verdict": verdict,
        "recommendation": rec,
    }


def summary_markdown(tsr: Dict[str, Any], project: str) -> str:
    lines = [f"# Test Summary Report — {project}", "", "_Structure: ISO/IEC/IEEE 29119-3._", ""]
    for key, title in (("scope", "Scope"), ("approach", "Approach")):
        lines += [f"## {title}", "", str(tsr[key]), ""]
    lines += ["## Deviations", ""] + [f"- {d}" for d in tsr["deviations"]] + [""]
    lines += ["## Coverage", ""] + [f"- {k}: {v}" for k, v in tsr["coverage"].items()] + [""]
    r = tsr["results"]
    lines += ["## Results", "", f"{r['executed']} executed: {r['passed']} passed, {r['failed']} failed, "
              f"{r['flaky']} flaky, {r['skipped']} skipped.", ""]
    lines += ["## Defects", "", f"{tsr['defects']['total']} product defect(s): " +
              ", ".join(f"{k} {v}" for k, v in tsr["defects"]["by_severity"].items()), ""]
    lines += ["## Residual risk", ""] + ([f"- {x}" for x in tsr["residual_risk"]] or ["- none identified"]) + [""]
    lines += ["## Recommendation", "", f"**{tsr['verdict']}** — {tsr['recommendation']}", ""]
    return "\n".join(lines)
