"""
ProjectStateManager — persistent per-project knowledge base.

Reads and writes  application_assets/projects/{project}/project_state.json.
All merge operations are additive: existing entries are updated field-by-field;
nothing is deleted unless explicitly marked status="deleted".

Neo4j Phase 2: replace the load/save I/O inside this module — the interface
(load, save, merge_*) stays identical so no orchestrator or agent code changes.
"""

import hashlib
import json
import os
import tempfile
from typing import Any, Dict, List

from tools.constants import PROJECTS_BASE as _ASSETS_BASE
from tools.discovery.paths import comprehension_scan_dir
_STATE_FILE = "project_state.json"
_SCHEMA_VERSION = "1.0"

_EMPTY_STATE_TEMPLATE: Dict[str, Any] = {
    "project": "",
    "schema_version": _SCHEMA_VERSION,
    "last_updated": "",
    "last_run_id": "",
    "discovery": {
        "dom_fingerprint": "",
        "brd_fingerprint": "",
        "last_discovered": "",
        "cached_output": {},
    },
    "summary": {
        "total_scenarios": 0,
        "total_test_cases": 0,
        "grounded_intents": 0,
        "passing_tests": 0,
        "failing_tests": 0,
    },
    "business_scenarios": {},
    "test_cases": {},
    "new_additions": [],
    "gaps": {
        "uncovered_scenarios": [],
        "ungrounded_intents": [],
    },
    "run_history": [],
}


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load(project_name: str) -> dict:
    """Read project_state.json; return an empty skeleton when missing."""
    path = _state_path(project_name)
    if not os.path.exists(path):
        state = json.loads(json.dumps(_EMPTY_STATE_TEMPLATE))
        state["project"] = project_name
        return state
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        # Ensure all top-level keys exist (forward-compat for older state files)
        template = json.loads(json.dumps(_EMPTY_STATE_TEMPLATE))
        for key, default in template.items():
            state.setdefault(key, default)
        return state
    except Exception:
        state = json.loads(json.dumps(_EMPTY_STATE_TEMPLATE))
        state["project"] = project_name
        return state


def save(project_name: str, state: dict) -> None:
    """Atomic write: write to a .tmp file then rename to avoid corruption."""
    path = _state_path(project_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(path), suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Fingerprinting — content-based change detection (not URL-based)
# ---------------------------------------------------------------------------

def compute_dom_fingerprint(project_name: str, module_id: str = None) -> str:
    """
    SHA256 of test_comprehension/dom_elements.json (or test_comprehension/modules/{module_id}/
    dom_elements.json when module_id is given); empty string if file missing.

    module_id must match whatever the discovery step actually scanned with —
    otherwise this fingerprints the wrong file and the skip-discovery-if-
    unchanged optimization silently stops working (always re-runs, or worse,
    always looks unchanged against a stale/unrelated module's file).
    """
    comp_root = os.path.join(_ASSETS_BASE, project_name, "test_comprehension")
    scan_dir = comprehension_scan_dir(comp_root, module_id)
    path = os.path.join(scan_dir, "dom_elements.json")
    return _file_sha256(path)


def compute_brd_fingerprint(brd_dir: str) -> str:
    """
    SHA256 over all BRD files in brd_dir (sorted for stability).
    Empty string if directory missing or empty.
    """
    if not brd_dir or not os.path.isdir(brd_dir):
        return ""
    files = sorted(
        os.path.join(brd_dir, f)
        for f in os.listdir(brd_dir)
        if os.path.isfile(os.path.join(brd_dir, f))
    )
    if not files:
        return ""
    h = hashlib.sha256()
    for fp in files:
        h.update(_file_sha256(fp).encode())
    return "sha256:" + h.hexdigest()


def discovery_needs_rerun(
    state: dict, project_name: str, brd_dir: str, module_id: str = None
) -> bool:
    """
    Return True if discovery should run.

    Skipped only when ALL of:
      1. project_state.json was previously saved (has stored fingerprints), AND
      2. business_scenarios were actually discovered and stored, AND
      3. DOM and BRD content are unchanged since that discovery.
    """
    stored = state.get("discovery", {})
    if not stored.get("dom_fingerprint") and not stored.get("brd_fingerprint"):
        return True  # no prior fingerprints — never discovered
    if not state.get("business_scenarios"):
        return True  # fingerprints stored but no discoveries saved — re-run
    current_dom = compute_dom_fingerprint(project_name, module_id)
    current_brd = compute_brd_fingerprint(brd_dir or "")
    return (
        current_dom != stored.get("dom_fingerprint", "")
        or current_brd != stored.get("brd_fingerprint", "")
    )


# ---------------------------------------------------------------------------
# Merge operations
# ---------------------------------------------------------------------------

def merge_discovery(
    state: dict, project_name: str, discovery_output: dict, brd_dir: str = "", module_id: str = None
) -> dict:
    """
    Upsert business scenarios from discovery output into state.
    Updates fingerprints. Never deletes existing scenarios.
    """
    scenarios_raw = discovery_output.get("scenarios", [])
    bs_map: dict = state.setdefault("business_scenarios", {})

    for s in scenarios_raw:
        bs_id = s.get("id") or s.get("scenario_id") or s.get("name", "")
        if not bs_id:
            continue
        existing = bs_map.get(bs_id, {})
        existing.update({
            "name": s.get("name", existing.get("name", bs_id)),
            "status": existing.get("status", "uncovered"),
        })
        existing.setdefault("test_cases", [])
        bs_map[bs_id] = existing

    disc = state.setdefault("discovery", {})
    disc["dom_fingerprint"] = compute_dom_fingerprint(project_name, module_id)
    disc["brd_fingerprint"] = compute_brd_fingerprint(brd_dir or "")
    disc["last_discovered"] = _now_iso()
    # Cache the raw output so orchestrator can skip re-running discovery on unchanged content
    disc["cached_output"] = {
        k: v for k, v in discovery_output.items()
        if k not in ("raw_dom", "html_content")  # exclude large blobs
    }

    state["summary"]["total_scenarios"] = len(bs_map)
    state = _recompute_gaps(state)
    return state


def merge_test_cases(
    state: dict,
    all_proposed: List[dict],
    approved_new: List[dict],
) -> dict:
    """
    Insert only approved_new test cases into state.
    Update test_data_hash on existing TCs if their data changed.
    approved_new items are added to state["new_additions"].
    """
    tc_map: dict = state.setdefault("test_cases", {})
    new_additions: list = state.setdefault("new_additions", [])

    # Update test_data_hash on existing TCs (detects data changes)
    for proposed in all_proposed:
        tc_id = proposed.get("test_case_id") or proposed.get("id", "")
        if tc_id in tc_map:
            new_hash = _dict_sha256(proposed)
            if tc_map[tc_id].get("test_data_hash") != new_hash:
                tc_map[tc_id]["test_data_hash"] = new_hash
                # Re-add to new_additions for re-execution
                if tc_id not in new_additions:
                    new_additions.append(tc_id)

    # Insert genuinely new approved TCs
    for tc in approved_new:
        tc_id = tc.get("test_case_id") or tc.get("id", "")
        if not tc_id or tc_id in tc_map:
            continue
        tc_map[tc_id] = {
            "name": tc.get("test_case_name") or tc.get("name", tc_id),
            "scenario": tc.get("business_scenario_id", ""),
            "suite": tc.get("test_case_type", "smoke"),
            "status": "pending",
            "test_data_hash": _dict_sha256(tc),
            "last_run": "",
            "last_run_id": "",
        }
        # Link TC to its scenario
        bs_id = tc.get("business_scenario_id", "")
        if bs_id and bs_id in state.get("business_scenarios", {}):
            sc = state["business_scenarios"][bs_id]
            if tc_id not in sc.get("test_cases", []):
                sc.setdefault("test_cases", []).append(tc_id)
            sc["status"] = "covered"

        if tc_id not in new_additions:
            new_additions.append(tc_id)

    state["summary"]["total_test_cases"] = len(tc_map)
    state = _recompute_gaps(state)
    return state


def merge_run_results(state: dict, run_id: str, execution_output: dict) -> dict:
    """
    Update pass/fail status on each TC from execution results.
    Appends a summary entry to run_history (capped at 20).
    """
    tc_map: dict = state.setdefault("test_cases", {})
    results: list = execution_output.get("results", [])
    today = _today()

    passed = 0
    failed = 0
    for r in results:
        tc_id = r.get("test_case_id") or r.get("id", "")
        status = "passing" if r.get("status") in ("pass", "passed", "success") else "failing"
        if tc_id in tc_map:
            tc_map[tc_id]["status"] = status
            tc_map[tc_id]["last_run"] = today
            tc_map[tc_id]["last_run_id"] = run_id
        if status == "passing":
            passed += 1
        else:
            failed += 1

    summary = execution_output.get("summary", {})
    history_entry = {
        "run_id": run_id,
        "timestamp": _now_iso(),
        "workflow": execution_output.get("workflow", ""),
        "status": execution_output.get("status", "unknown"),
        "passed": summary.get("passed", passed),
        "failed": summary.get("failed", failed),
        "total": summary.get("total", passed + failed),
    }
    history: list = state.setdefault("run_history", [])
    history.insert(0, history_entry)
    state["run_history"] = history[:20]  # keep last 20

    state["summary"]["passing_tests"] = sum(
        1 for tc in tc_map.values() if tc.get("status") == "passing"
    )
    state["summary"]["failing_tests"] = sum(
        1 for tc in tc_map.values() if tc.get("status") == "failing"
    )
    return state


def graduate_additions(state: dict, run_results: dict) -> dict:
    """
    Move successfully executed TCs from new_additions into their permanent suite.
    TCs that failed stay in new_additions for the next run.
    """
    new_additions: list = state.get("new_additions", [])
    results: list = run_results.get("results", [])
    passed_ids = {
        r.get("test_case_id") or r.get("id", "")
        for r in results
        if r.get("status") in ("pass", "passed", "success")
    }
    # Keep only those that did NOT pass
    state["new_additions"] = [tc_id for tc_id in new_additions if tc_id not in passed_ids]
    return state


# ---------------------------------------------------------------------------
# Suite building
# ---------------------------------------------------------------------------

def build_new_additions_suite(state: dict) -> List[str]:
    """
    Return TC ids that should be executed this session:
    - TCs in state["new_additions"] (not yet graduated)
    - Existing TCs whose test_data_hash changed (already handled in merge_test_cases)
    """
    return list(state.get("new_additions", []))


def write_new_additions_yaml(state: dict, project_name: str) -> str:
    """
    Write artifacts/test_suites/new_additions.yaml for the execution agent.
    Returns the file path. Returns "" if nothing to add.
    """
    ids = build_new_additions_suite(state)
    if not ids:
        return ""

    tc_map = state.get("test_cases", {})
    entries = []
    for tc_id in ids:
        tc = tc_map.get(tc_id, {})
        entries.append({
            "test_case_id": tc_id,
            "test_case_name": tc.get("name", tc_id),
            "suite": "new_additions",
            "scenario": tc.get("scenario", ""),
            "status": tc.get("status", "pending"),
        })

    import yaml
    suite_dir = os.path.join(_ASSETS_BASE, project_name, "test_creation", "test_suites")
    os.makedirs(suite_dir, exist_ok=True)
    path = os.path.join(suite_dir, "new_additions.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"suite": "new_additions", "test_cases": entries},
            f,
            default_flow_style=False,
            allow_unicode=True,
        )
    return path


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------

def _recompute_gaps(state: dict) -> dict:
    bs_map = state.get("business_scenarios", {})
    tc_map = state.get("test_cases", {})

    uncovered = [
        bs_id for bs_id, sc in bs_map.items()
        if not sc.get("test_cases")
    ]
    ungrounded: list = []  # populated if locator data available (future)

    state["gaps"] = {
        "uncovered_scenarios": uncovered,
        "ungrounded_intents": ungrounded,
    }
    return state


# ---------------------------------------------------------------------------
# Summary display
# ---------------------------------------------------------------------------

def print_summary(state: dict) -> None:
    """Print a human-readable project state summary to stdout."""
    proj = state.get("project", "?")
    summary = state.get("summary", {})
    gaps = state.get("gaps", {})
    new_adds = state.get("new_additions", [])
    history = state.get("run_history", [])
    last_run = history[0] if history else {}

    print(f"\n{'='*50}")
    print(f"  Project: {proj}")
    print(f"  Last updated: {state.get('last_updated', 'never')}")
    print(f"  Last run ID:  {state.get('last_run_id', 'none')}")
    print(f"{'='*50}")
    print(f"  Scenarios:    {summary.get('total_scenarios', 0)}")
    print(f"  Test cases:   {summary.get('total_test_cases', 0)}")
    print(f"  Passing:      {summary.get('passing_tests', 0)}")
    print(f"  Failing:      {summary.get('failing_tests', 0)}")
    print(f"  New additions:{len(new_adds)}")
    if gaps.get("uncovered_scenarios"):
        print(f"  Gaps (uncovered scenarios): {gaps['uncovered_scenarios']}")
    if last_run:
        print(f"  Last run:     {last_run.get('timestamp', '?')} — {last_run.get('status', '?')}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _state_path(project_name: str) -> str:
    return os.path.join(_ASSETS_BASE, project_name, _STATE_FILE)


def _file_sha256(path: str) -> str:
    if not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _dict_sha256(d: dict) -> str:
    serialised = json.dumps(d, sort_keys=True, ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(serialised).hexdigest()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    from datetime import date
    return date.today().isoformat()
