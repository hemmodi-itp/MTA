"""
mta_results.py — reader for the MTA Playwright reporter's output (Phase 4.2).

The reporter (application_assets/_shared/runtime/reporters/mta-reporter.ts) writes
test_execution/reports/mta/{ts}.mta_results.json (contract `mta_results`, schema_version 2):

    {schema_version, artifact, run_id, project, shard: {current, total} | null,
     started_at, finished_at, status, totals: {total, passed, failed, flaky, skipped, timedOut, interrupted},
     tests: [{test_id, title, title_path, spec_file, line, project, tags, annotations,
              tc_id, case_id, scenario_id, ac_ids, status, outcome, expected_status,
              retries, duration_ms, attempts: [{retry, status, duration_ms, error}],
              attachments: [{name, content_type, path}]}]}

`to_execution_results()` converts it to UIExecutionAgent's per-test result shape, which
tools.requirements.traceability.apply_results consumes (pw_status carries the MTA status; a flaky test
keeps status "flaky", it is never turned into a pass). Since Phase 4.7 this is UIExecutionAgent's source of
truth for per-test results (the Playwright JSON report is the fallback): result status is
success | flaky | failed (failed, timedOut, interrupted) | skipped.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

MTA_STATUSES = ("passed", "failed", "flaky", "skipped", "timedOut", "interrupted")

_STATUS_TO_RESULT = {"passed": "success", "flaky": "flaky", "skipped": "skipped"}

# Same spec-id scheme as ui_execution/agent.py::_SPEC_ID_RE ("M03_BS_006", legacy "BS-001" / "SC-001") —
# test_suite.json stamping and the reports key results by it.
_SPEC_ID_RE = re.compile(r"([A-Za-z]+\d+_BS_\d+|BS-\d+|SC-\d+)")


def load_mta_results(path: str) -> Optional[Dict[str, Any]]:
    """The parsed file, or None when it is missing or unreadable (never raises)."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("artifact") == "mta_results" else None


def to_execution_results(doc: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in (doc or {}).get("tests") or []:
        if not isinstance(t, dict):
            continue
        status = str(t.get("status") or "")
        attempts = [a for a in (t.get("attempts") or []) if isinstance(a, dict)]
        spec_file = str(t.get("spec_file") or "")
        m = _SPEC_ID_RE.search(spec_file)
        r: Dict[str, Any] = {
            "spec_file": spec_file,
            "test_case_id": m.group(1) if m else "",
            "business_scenario_id": m.group(1) if m else "",
            "test_title": str(t.get("title") or ""),
            "project": t.get("project"),
            "status": _STATUS_TO_RESULT.get(status, "failed"),
            "pw_status": status,
            "flaky": status == "flaky",
            "duration_ms": t.get("duration_ms", 0),
            "first_attempt_duration_ms": attempts[0].get("duration_ms", 0) if attempts else 0,
            "errors": [a["error"] for a in attempts if a.get("error")],
            "tags": list(t.get("tags") or []),
            "annotations": list(t.get("annotations") or []),
            "attachments": list(t.get("attachments") or []),
            "retries": int(t.get("retries") or 0),
            "failed_step": next((a.get("failed_step") for a in reversed(attempts) if a.get("failed_step")), None),
            "cleanup_failures": list(t.get("cleanup_failures") or []),
            "comment": "",
            "no_interaction_close": False,
        }
        for key in ("tc_id", "case_id", "scenario_id"):
            if t.get(key):
                r[key] = t[key]
        if t.get("ac_ids"):
            r["ac_ids"] = list(t["ac_ids"])
        out.append(r)
    return out


def totals(doc: Optional[Dict[str, Any]]) -> Dict[str, int]:
    base = {k: 0 for k in ("total",) + MTA_STATUSES}
    base.update({k: int(v) for k, v in ((doc or {}).get("totals") or {}).items() if k in base})
    return base
