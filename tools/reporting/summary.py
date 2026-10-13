"""Phase 11-lean: executive summary metrics, traceability CSV, defect list and quality gates. Pure Python.

Flags in project.yaml (absent = OFF):
    reporting:     {enhanced: true}                       # executive summary / defects / CSV in the report
    quality_gates: {p0_pass_rate: 100, requirement_coverage: 90}   # failed gate -> exit code 1 (CLI below)

CLI: python -m tools.reporting.summary <report.json>   (exit 0 = gates passed or none configured, 1 = failed)
"""

import csv
import io
import json
import os
import sys
from typing import Any, Dict, List, Optional

PRIORITIES = ("P0", "P1", "P2", "P3")
_GATE_KEYS = ("p0_pass_rate", "requirement_coverage")


def load_project_yaml(project_dir: str) -> dict:
    import yaml
    try:
        with open(os.path.join(project_dir, "project.yaml"), encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def enhanced_enabled(raw: dict) -> bool:
    return bool((raw.get("reporting") or {}).get("enhanced"))


def gates_config(raw: dict) -> Dict[str, float]:
    block = raw.get("quality_gates")
    if not isinstance(block, dict):
        return {}
    return {k: float(block[k]) for k in _GATE_KEYS if isinstance(block.get(k), (int, float))}


def _is_pass(r: dict) -> bool:
    return str(r.get("pw_status") or r.get("status") or "").lower() in ("passed", "expected", "success")


def _is_skipped(r: dict) -> bool:
    return str(r.get("pw_status") or r.get("status") or "").lower() == "skipped"


def _priority_by_tc(plans: dict) -> Dict[str, str]:
    out = {}
    for plan in ((plans or {}).get("plans") or {}).values():
        for t in (plan.get("tests") or []) if isinstance(plan, dict) else []:
            if isinstance(t, dict) and t.get("tc_id") and t.get("priority"):
                out[t["tc_id"]] = t["priority"]
    return out


def pass_rate_by_priority(results: List[dict], tc_priority: Dict[str, str]) -> Dict[str, Optional[dict]]:
    """{P0: {passed, executed, rate} | None}; skipped tests are not executed. Unprioritised tests are ignored."""
    acc = {p: [0, 0] for p in PRIORITIES}
    for r in results:
        p = tc_priority.get(r.get("tc_id") or "")
        if p not in acc or _is_skipped(r):
            continue
        acc[p][1] += 1
        acc[p][0] += 1 if _is_pass(r) else 0
    return {p: ({"passed": a, "executed": n, "rate": round(100.0 * a / n, 1)} if n else None)
            for p, (a, n) in acc.items()}


def compute_summary(results: List[dict], trace: Optional[dict], plans: dict, suite: dict,
                    triage: Optional[dict], agent_quality: Optional[dict]) -> Dict[str, Any]:
    ts = (trace or {}).get("summary") or {}
    weak = sum(len(s.get("weak_oracle") or []) for s in (suite or {}).get("specs") or [])
    failed = [r for r in results if not _is_pass(r) and not _is_skipped(r)
              and str(r.get("pw_status") or "").lower() != "flaky"]
    tag_fail = lambda tag: sum(1 for r in failed if tag in (r.get("tags") or []))  # noqa: E731
    dims = ((agent_quality or {}).get("dimensions") or {})
    return {
        "requirement_coverage": ts.get("coverage_pct"),
        "acs_covered": ts.get("acs_covered"), "acs_automatable": ts.get("acs_automatable"),
        "pass_rate_by_priority": pass_rate_by_priority(results, _priority_by_tc(plans)),
        "product_defects": (triage["counts"].get("product_defect", 0) if triage else None),
        "a11y_findings": tag_fail("@a11y"), "security_findings": tag_fail("@security"),
        "weak_oracle": weak,
        "agent_dimensions": {d: v.get("outcome") for d, v in dims.items()} if dims else None,
    }


def evaluate_gates(summary: dict, gates: Dict[str, float]) -> Dict[str, Any]:
    """{verdict: PASS|FAIL|NO_GATES, gates: [{gate, threshold, actual, ok}]}. Missing data fails (no silent pass),
    except a P0 rate with zero executed P0 tests (nothing to fail)."""
    rows = []
    for gate, thr in gates.items():
        if gate == "p0_pass_rate":
            p0 = summary["pass_rate_by_priority"].get("P0")
            actual = p0["rate"] if p0 else None
            ok = True if p0 is None else actual >= thr
        else:
            actual = summary.get("requirement_coverage")
            ok = actual is not None and actual >= thr
        rows.append({"gate": gate, "threshold": thr, "actual": actual, "ok": ok})
    verdict = "NO_GATES" if not rows else ("PASS" if all(r["ok"] for r in rows) else "FAIL")
    return {"verdict": verdict, "gates": rows}


def gate_exit_code(gate_result: Optional[dict]) -> int:
    return 1 if gate_result and gate_result.get("verdict") == "FAIL" else 0


def traceability_csv(trace: Optional[dict]) -> str:
    """AC × tests × latest result; an AC with no test gets one row saying why."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["ac_id", "priority", "criterion", "ac_status", "tc_id", "test_title", "latest_result", "not_tested_reason"])
    for a in (trace or {}).get("acs") or []:
        if a.get("children"):
            continue
        reason = a.get("uncovered_reason") or {}
        base = [a.get("id"), a.get("priority"), a.get("statement"), a.get("status")]
        tests = a.get("tests") or []
        if not tests:
            w.writerow(base + ["", "", "not_run", reason.get("code", "")])
        for t in tests:
            w.writerow(base + [t.get("tc_id"), t.get("title"), t.get("status"), ""])
    return buf.getvalue()


def not_tested(trace: Optional[dict]) -> List[dict]:
    return [{"id": u.get("id"), "priority": u.get("priority"), "code": u.get("code") or "unknown",
             "detail": u.get("detail") or ""} for u in (trace or {}).get("uncovered") or []]


def _step_text(s: dict) -> str:
    parts = [str(s.get("action", "")), str(s.get("locator_key") or s.get("target") or ""), str(s.get("value") or "")]
    return " ".join(p for p in parts if p)


def _plan_test(plans: dict, tc_id: str) -> Optional[dict]:
    for plan in ((plans or {}).get("plans") or {}).values():
        for t in (plan.get("tests") or []) if isinstance(plan, dict) else []:
            if isinstance(t, dict) and t.get("tc_id") == tc_id:
                return t
    return None


def _first_line(errors: list) -> str:
    for e in errors or []:
        line = str(e or "").strip().splitlines()
        if line:
            return line[0][:300]
    return ""


def build_defects(results: List[dict], triage: Optional[dict], plans: dict) -> List[dict]:
    """One entry per triaged product_defect: title, linked ACs, steps (from the plan), expected vs actual, evidence."""
    if not triage:
        return []
    from tools.triage.triage import PRODUCT_DEFECT, _spec_key
    bad = {(_spec_key(t["spec_file"]), t["test_name"]) for t in triage["tests"] if t["verdict"] == PRODUCT_DEFECT}
    out = []
    for r in results:
        if (_spec_key(r.get("spec_file") or ""), r.get("test_title")) not in bad:
            continue
        pt = _plan_test(plans, r.get("tc_id") or "") or {}
        steps = [_step_text(s) for s in pt.get("steps") or [] if isinstance(s, dict)]
        expected = "; ".join(f"{s.get('message') or _step_text(s)}" for s in pt.get("steps") or []
                             if isinstance(s, dict) and str(s.get("action", "")).startswith("verify"))
        atts = r.get("attachments") or []
        link = lambda kind: next((a.get("path") for a in atts if kind in str(a.get("name", "")).lower()  # noqa: E731
                                  or kind in str(a.get("content_type", "")).lower()), None)
        out.append({"title": r.get("test_title"), "tc_id": r.get("tc_id"),
                    "ac_ids": r.get("ac_ids") or pt.get("ac_ids") or [], "steps": steps,
                    "expected": expected, "actual": _first_line(r.get("errors")),
                    "screenshot": link("screenshot") or link("image"), "trace": link("trace")})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        gates = (json.load(fh).get("quality") or {}).get("gates")
    if gates:
        for g in gates["gates"]:
            print(f"{'PASS' if g['ok'] else 'FAIL'} {g['gate']}: {g['actual']} (need >= {g['threshold']})")
    return gate_exit_code(gates)


if __name__ == "__main__":
    sys.exit(main())
