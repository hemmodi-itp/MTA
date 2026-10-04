"""paths.py — where runtime artifacts live (shared by the Playwright Executor and Evidence Collection).

Durable per-run folder, separate from the temporary workspace that is deleted after a run:
<AQP_ARTIFACT_DIR or <repo>/.aqp_artifacts>/runs/<run_id>. The web app serves files from the same place
(frontend/src/app/api/runs/[runId]/execution-files).
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def artifact_root() -> Path:
    return Path(os.environ.get("AQP_ARTIFACT_DIR") or REPO_ROOT / ".aqp_artifacts") / "runs"


def run_artifact_dir(run_id: str) -> Path:
    safe = "".join(ch for ch in (run_id or "") if ch.isalnum() or ch in "-_")[:64] or "adhoc"
    return artifact_root() / safe
