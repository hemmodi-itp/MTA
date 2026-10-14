"""
audit.py — Phase 6.9 heal audit log: one JSON line per heal decision in
test_execution/reports/healing_audit.jsonl (append-only).

Fields: timestamp, run_id, mode, kind (locator_map | spec_patch), target, test, before, after, evidence,
confidence (identity score, when there is one), approver ("auto" for an applied heal, "pending" for a proposal or
a refusal waiting for a person), outcome (applied | proposed | refused | reverted | burn_in_failed | verified).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

AUDIT_FILE = "healing_audit.jsonl"


def append(reports_dir: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    row.setdefault("approver", "auto" if row.get("outcome") in ("applied", "verified", "reverted") else "pending")
    if not reports_dir:          # no reports folder for this run (unit contexts) — nothing to append to
        return row
    os.makedirs(reports_dir, exist_ok=True)
    with open(os.path.join(reports_dir, AUDIT_FILE), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row


def read(reports_dir: str, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    path = os.path.join(reports_dir, AUDIT_FILE)
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if run_id is None or row.get("run_id") == run_id:
                rows.append(row)
    return rows
