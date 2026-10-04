import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _run_filename(run_id: str, project: Optional[str] = None, started_at: Optional[datetime] = None) -> str:
    ts = (started_at or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    slug = f"_{project}" if project else ""
    return f"{ts}{slug}_{run_id}.json"


def save_workflow_run(
    run_id: str,
    payload: Dict[str, Any],
    base_dir: Optional[str] = None,
    project: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> str:
    base_dir = os.path.abspath(base_dir or os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(base_dir, "workflow_runs")
    ensure_directory(path)
    filename = os.path.join(path, _run_filename(run_id, project, started_at))
    with open(filename, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return filename


def load_workflow_run(run_id: str, base_dir: Optional[str] = None) -> Dict[str, Any]:
    base_dir = os.path.abspath(base_dir or os.path.join(os.path.dirname(__file__), ".."))
    runs_dir = os.path.join(base_dir, "workflow_runs")
    # Exact match first (legacy files named by run_id only)
    exact = os.path.join(runs_dir, f"{run_id}.json")
    if os.path.exists(exact):
        with open(exact, "r", encoding="utf-8") as handle:
            return json.load(handle)
    # Timestamped match: find any file whose name ends with _{run_id}.json
    for name in os.listdir(runs_dir):
        if name.endswith(f"_{run_id}.json"):
            with open(os.path.join(runs_dir, name), "r", encoding="utf-8") as handle:
                return json.load(handle)
    raise FileNotFoundError(f"No workflow run found for run_id={run_id}")
