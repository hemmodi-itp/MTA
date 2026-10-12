"""
shards.py — Playwright --shard planning for UIExecutionAgent (Phase 4.8).

Layout of one sharded run (run id = the run's timestamp, or the caller's `run_id` for CI jobs):

    reports/blob/<run_id>/shard-<i>/report-<i>.zip     blob reporter output (one folder per shard,
                                                       because the blob reporter empties its folder)
    reports/test-results/<ts>/shard-<i>/               --output per shard (Playwright empties it too)

A local `shards: n` run executes every shard (sequentially, or `max_parallel_shards` at a time) with
only the list + blob reporters, then merges (tools/execution/merge_reports.py) into the run's normal
json / html / junit / mta outputs. A single `shard: "i/n"` run (a CI job) keeps the normal reporters
and also writes its blob, to be merged later with `merge_run: <run_id>`.
"""

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_SHARD_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


class ShardSpecError(ValueError):
    pass


def parse_shard(spec) -> Optional[Tuple[int, int]]:
    """'2/3' -> (2, 3); None/'' -> None; anything else (0/3, 4/3, 'x') -> ShardSpecError."""
    if spec in (None, ""):
        return None
    m = _SHARD_RE.match(str(spec))
    if not m:
        raise ShardSpecError(f"invalid shard '{spec}' — expected i/n, e.g. 1/2")
    i, n = int(m.group(1)), int(m.group(2))
    if n < 1 or not 1 <= i <= n:
        raise ShardSpecError(f"invalid shard '{spec}' — need 1 <= i <= n")
    return i, n


def blob_root(reports_dir: str, run_id: str) -> str:
    return os.path.join(reports_dir, "blob", run_id)


def shard_blob_dir(reports_dir: str, run_id: str, index: int) -> str:
    return os.path.join(blob_root(reports_dir, run_id), f"shard-{index}")


@dataclass
class ShardRun:
    index: int
    total: int
    cmd: List[str]
    env: Dict[str, str]
    blob_dir: str
    output_dir: str


def _with_output(cmd: List[str], output_dir: str) -> List[str]:
    out = [a for a in cmd if not a.startswith("--output=") and not a.startswith("--shard=")]
    return out + [f"--output={output_dir}"]


def plan_shards(cmd: List[str], env: Dict[str, str], total: int, reports_dir: str, run_id: str,
                test_results_dir: str, blob_only: bool = True) -> List[ShardRun]:
    """One command/env per shard. blob_only=True (local multi-shard run) tells the config builder to
    use only the list + blob reporters; the merge then writes the normal reports once."""
    runs = []
    for i in range(1, total + 1):
        out_dir = os.path.join(test_results_dir, f"shard-{i}")
        blob = shard_blob_dir(reports_dir, run_id, i)
        shard_env = {**env, "PW_BLOB_DIR": blob}
        if blob_only:
            shard_env["MTA_BLOB_ONLY"] = "1"
        runs.append(ShardRun(i, total, _with_output(cmd, out_dir) + [f"--shard={i}/{total}"], shard_env, blob, out_dir))
    return runs


def single_shard(cmd: List[str], env: Dict[str, str], index: int, total: int, reports_dir: str,
                 run_id: str, invocation: str = "") -> Tuple[List[str], Dict[str, str]]:
    """A CI-style single shard: normal reporters + a blob for a later merge. `invocation` (the run's
    timestamp) gives every Playwright invocation its own folder: a modular project split per module
    runs once per module, and the blob reporter empties its folder at start."""
    cmd = [a for a in cmd if not a.startswith("--shard=")] + [f"--shard={index}/{total}"]
    folder = shard_blob_dir(reports_dir, run_id, index) + (f"-{invocation}" if invocation else "")
    return cmd, {**env, "PW_BLOB_DIR": folder}
