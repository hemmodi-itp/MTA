"""
review_queue.py — writes entries to human_review_queue.json for anything that
needs a human's attention: a Python fallback being used, an LLM plan reporting
a capability gap, or a dom_elements.json/locator_map.json merge finding drift.

A HUMAN_REVIEW route means all LLM tiers failed and the Python fallback was used.
The entry is logged here so QA can prioritise which scenarios need manual attention.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_QUEUE_FILE = "human_review_queue.json"


def _append_queue_entry(output_dir: str, entry: Dict[str, Any]) -> None:
    os.makedirs(output_dir, exist_ok=True)
    queue_path = os.path.join(output_dir, _QUEUE_FILE)
    queue: list = []
    if os.path.exists(queue_path):
        try:
            with open(queue_path, encoding="utf-8") as f:
                queue = json.load(f)
        except Exception:
            queue = []
    queue.append(entry)
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


def flag_for_human_review(
    project_name: str,
    agent_name: str,
    request: Dict[str, Any],
    exc: Exception,
    output_dir: str = ".",
) -> None:
    """Append one entry to human_review_queue.json in output_dir."""
    _append_queue_entry(output_dir, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "python_fallback",
        "project": project_name,
        "agent": agent_name,
        "scenario_id": request.get("scenario_id", request.get("project_name", "unknown")),
        "error": str(exc),
        "error_type": type(exc).__name__,
        "action": "Python fallback used — verify output accuracy",
    })


def flag_missing_capability(
    project_name: str,
    scenario_id: str,
    missing_actions: List[str],
    missing_locators: List[str],
    output_dir: str = ".",
) -> None:
    """Append one entry when a ScriptGenerationAgent plan reports an action or
    locator it needed but wasn't in the allowed vocabulary/locator_map for
    that scenario — reported instead of guessed, per the action-library
    hallucination-minimization design."""
    if not missing_actions and not missing_locators:
        return
    _append_queue_entry(output_dir, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": "missing_capability",
        "project": project_name,
        "scenario_id": scenario_id,
        "missing_actions": missing_actions,
        "missing_locators": missing_locators,
        "action": "Add the missing action to ActionEngine/ALLOWED_ACTIONS or the "
                   "missing element to locator_map.json, then regenerate this scenario",
    })


def record_locator_drift(
    project_name: str,
    module_id: str,
    added: List[str],
    updated: List[str],
    possibly_removed: List[str],
    output_dir: str = ".",
    kind: str = "dom_drift",
    source: Optional[str] = None,
) -> None:
    """Append one entry when a dom_elements.json or locator_map.json merge
    finds elements added, updated, or possibly removed since the last run.
    Never fires for a no-op merge (all three lists empty). *kind* distinguishes
    a raw dom_elements.json merge ("dom_drift") from a locator_map.json merge
    ("locator_map_drift") — both write into the same human_review_queue.json.
    """
    if not added and not updated and not possibly_removed:
        return
    _append_queue_entry(output_dir, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "project": project_name,
        "module_id": module_id,
        "source": source,
        "added": added,
        "updated": updated,
        "possibly_removed": possibly_removed,
        "action": "Review added/updated/possibly-removed elements — nothing was "
                   "deleted automatically; a possibly-removed entry may be stale "
                   "and worth pruning by hand once confirmed gone",
    })
