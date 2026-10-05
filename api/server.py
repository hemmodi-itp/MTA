"""
MTA agent-evaluation service — HTTP entry point for the web app.

    .venv\\Scripts\\python -m uvicorn api.server:app --host 127.0.0.1 --port 8100

The Next.js app creates the Project + Run rows in Postgres, then calls
POST /runs/{id}/start. A background poller also picks up any run still `queued`
(e.g. created while this service was down, or waiting for a free worker), so the
trigger is an optimisation, not a requirement.

Run lifecycle guarantees:
  * a run is claimed (queued → cloning, atomic in Postgres) only when a worker slot is free, so a waiting run
    stays `queued` and survives a restart;
  * every running run sends a heartbeat (Run.heartbeatAt) and checks Run.cancelRequested every 30 s;
  * a sweeper fails runs whose heartbeat stopped (STALE_AFTER_S) — e.g. a crashed process — scoped to those runs;
  * on startup, runs left mid-flight by a previous process are failed with an explanation;
  * run artifacts older than AQP_ARTIFACT_RETENTION_DAYS (default 30) or belonging to deleted runs are removed.

Env: GOOGLE_API_KEY (repo-root .env), DATABASE_URL (repo-root .env, or read from
frontend/.env), AQP_BACKEND_TOKEN (shared secret with the web app; without it only
loopback callers are accepted), AQP_MAX_CONCURRENT_RUNS (default 2), GITHUB_TOKEN,
AQP_ARTIFACT_RETENTION_DAYS (default 30), AQP_ALLOW_PRIVATE_TARGETS (local dev only).
"""

import hmac
import json
import logging
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml
from dotenv import dotenv_values, load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
if not os.environ.get("DATABASE_URL"):
    frontend_url = dotenv_values(REPO_ROOT / "frontend" / ".env").get("DATABASE_URL")
    if frontend_url:
        os.environ["DATABASE_URL"] = frontend_url
if not os.environ.get("AQP_BACKEND_TOKEN"):
    frontend_token = dotenv_values(REPO_ROOT / "frontend" / ".env").get("AQP_BACKEND_TOKEN")
    if frontend_token:
        os.environ["AQP_BACKEND_TOKEN"] = frontend_token


def _load_yaml(name: str) -> dict:
    with open(REPO_ROOT / "workflows" / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _configure_service_logging(settings: dict) -> None:
    """Console + logs/service.log for the service's own loggers (agent_eval.*, agent.*, connectors.*, workflow.*)."""
    level = getattr(logging, str((settings.get("logging") or {}).get("level", "INFO")).upper(), logging.INFO)
    (REPO_ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file_handler = logging.FileHandler(REPO_ROOT / "logs" / "service.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    for name in ("agent_eval", "agent", "connectors", "workflow", "engines", "tools"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.handlers = [console, file_handler]
        lg.propagate = False
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(console)
    root.setLevel(logging.WARNING)


SETTINGS = _load_yaml("settings.yaml")
_configure_service_logging(SETTINGS)

from agents.registry_setup import build_default_registry  # noqa: E402
from api.pipeline import HEARTBEAT_S, SERVICE_STOPPING, AgentEvaluationPipeline  # noqa: E402
from engines.report.pdf import html_to_pdf  # noqa: E402
from engines.runtime.paths import artifact_root  # noqa: E402
from tools.agent_eval.copilot import answer as copilot_answer  # noqa: E402
from tools.agent_eval.run_store import RunStore  # noqa: E402
from tools.shared import get_logger  # noqa: E402

POLL_SECONDS = 5
SWEEP_SECONDS = 60
STALE_AFTER_S = 10 * 60
STARTUP_STALE_AFTER_S = 3 * HEARTBEAT_S
MAX_RUNS = max(1, int(os.environ.get("AQP_MAX_CONCURRENT_RUNS", "2")))
RETENTION_DAYS = int(os.environ.get("AQP_ARTIFACT_RETENTION_DAYS", "30"))
logger = get_logger("agent_eval.api")

store = RunStore()
pipeline = AgentEvaluationPipeline(SETTINGS, _load_yaml("agents.yaml"), build_default_registry(scope="mta"), store)
_active: Set[str] = set()
_lock = threading.Lock()
_stop = threading.Event()


def _submit(run_id: str) -> bool:
    """Claim a queued run (atomic in Postgres) and start it — only when a worker slot is free."""
    with _lock:
        if run_id in _active or len(_active) >= MAX_RUNS or not store.claim_run(run_id):
            return False
        _active.add(run_id)

    def work() -> None:
        try:
            pipeline.run(run_id)
        finally:
            with _lock:
                _active.discard(run_id)
            _wake.set()  # a slot is free: pick up the next queued run now

    # daemon: stopping the service must not wait an hour for a browser run; the next start fails it cleanly
    threading.Thread(target=work, name=f"aqp-run-{run_id[-6:]}", daemon=True).start()
    logger.info(f"Run {run_id} started ({len(_active)}/{MAX_RUNS} slots busy)")
    return True


_wake = threading.Event()


def _poll_queued() -> None:
    while not _stop.is_set():
        _wake.wait(POLL_SECONDS)
        _wake.clear()
        if _stop.is_set():
            return
        try:
            for run_id in store.queued_run_ids():
                if len(_active) >= MAX_RUNS:
                    break
                _submit(run_id)
        except Exception as exc:
            logger.warning(f"Queued-run poll failed: {exc}")


def _sweep() -> None:
    """Fail runs whose worker died (stale heartbeat) and prune old artifacts."""
    last_prune = 0.0
    while not _stop.wait(SWEEP_SECONDS):
        try:
            with _lock:
                mine = list(_active)
            stale = store.fail_orphaned_runs("The evaluation stopped responding (no heartbeat for 10 minutes) and "
                                             "was stopped. Start a new run.", STALE_AFTER_S, exclude=mine)
            if stale:
                logger.warning(f"Failed {len(stale)} stalled run(s): {', '.join(stale)}")
        except Exception as exc:
            logger.warning(f"Stale-run sweep failed: {exc}")
        if time.monotonic() - last_prune > 6 * 3600:
            last_prune = time.monotonic()
            try:
                _prune_artifacts()
            except Exception as exc:
                logger.warning(f"Artifact pruning failed: {exc}")


def _prune_artifacts() -> None:
    root = artifact_root()
    if not root.exists():
        return
    existing = {r["id"] for r in store.db.query('SELECT "id" FROM "Run"')}
    cutoff = time.time() - RETENTION_DAYS * 86400
    removed = 0
    for d in root.iterdir():
        if not d.is_dir() or d.name in _active:
            continue
        if d.name not in existing or d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    if removed:
        logger.info(f"Pruned {removed} run artifact folder(s) (deleted runs or older than {RETENTION_DAYS} days)")


def pipeline_requeue(run_id: str) -> bool:
    from tools.agent_eval.run_store import RESTART_MARK
    return store.requeue_interrupted(run_id, f"{RESTART_MARK}: the MTA service was stopped or restarted while this run "
                                             "was in progress, so it starts again from the beginning.")


def _warm_llm_client() -> None:
    try:
        from connectors.llm.gemini import GeminiConnector
        GeminiConnector()._client()
        logger.info("Gemini client ready")
    except Exception as exc:
        logger.warning(f"Gemini client warm-up failed: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # runs a previous process left mid-flight (hard kill / crash): restart each once, fail it if it was already restarted
    requeued = [rid for rid in store.orphaned_run_ids(STARTUP_STALE_AFTER_S) if pipeline_requeue(rid)]
    orphaned = store.fail_orphaned_runs("The MTA service stopped during this run twice in a row. Start a new run.",
                                        STARTUP_STALE_AFTER_S)
    if requeued or orphaned:
        logger.warning(f"Interrupted runs: {len(requeued)} requeued, {len(orphaned)} marked failed")
    if not os.environ.get("AQP_BACKEND_TOKEN"):
        logger.warning("AQP_BACKEND_TOKEN is not set: only callers on this machine (loopback) are accepted. "
                       "Set the same value in .env and frontend/.env for any non-local setup.")
    threading.Thread(target=_poll_queued, name="aqp-poller", daemon=True).start()
    threading.Thread(target=_sweep, name="aqp-sweeper", daemon=True).start()
    # Build the shared Gemini client up front (SSL setup can be slow on some machines)
    # so the first run doesn't pay for it mid-step.
    threading.Thread(target=_warm_llm_client, name="aqp-llm-warmup", daemon=True).start()
    _wake.set()
    yield
    # graceful stop (Ctrl+C / reload): running runs stop at their next checkpoint and are queued again
    SERVICE_STOPPING.set()
    _stop.set()
    _wake.set()
    with _lock:
        active = list(_active)
    if active:
        logger.warning(f"Stopping: {len(active)} run(s) in progress will restart when the service is back.")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and _active:
            time.sleep(0.5)
        for rid in list(_active):  # steps that could not stop in time: requeue from here
            pipeline_requeue(rid)


app = FastAPI(title="MTA agent-evaluation service", lifespan=lifespan)


def _check_token(token: Optional[str], request: Request) -> None:
    expected = os.environ.get("AQP_BACKEND_TOKEN")
    if expected:
        if not token or not hmac.compare_digest(token, expected):
            raise HTTPException(status_code=401, detail="invalid backend token")
        return
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=401, detail="a backend token is required for non-local callers")


@app.get("/health")
def health() -> dict:
    db_ok = True
    try:
        store.db.ping()
    except Exception:
        db_ok = False
    out = {"ok": db_ok, "database": db_ok, "llm_key_configured": bool(os.environ.get("GOOGLE_API_KEY")),
           "active_runs": len(_active), "max_runs": MAX_RUNS}
    try:
        from connectors.llm.gemini import llm_stats
        out["llm"] = llm_stats()
    except Exception:
        pass
    return out


class CopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: str = Field(default="", max_length=80_000)
    scope: str = Field(default="portfolio", max_length=200)
    history: List[Dict[str, str]] = Field(default_factory=list, max_length=20)


@app.post("/copilot")
def copilot(body: CopilotRequest, request: Request, x_aqp_token: Optional[str] = Header(default=None)) -> dict:
    """Grounded answer for the web app's Copilot; the context is built (and access-checked) by the web app."""
    _check_token(x_aqp_token, request)
    try:
        return {"answer": copilot_answer(body.question, body.context, body.scope, body.history)}
    except Exception as exc:
        logger.warning(f"Copilot failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="The language model is unavailable right now.")


@app.post("/runs/{run_id}/start", status_code=202)
def start_run(run_id: str, request: Request, x_aqp_token: Optional[str] = Header(default=None)) -> dict:
    _check_token(x_aqp_token, request)
    row = store.load_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    if row["status"] != "queued":
        return {"run_id": run_id, "started": False, "status": row["status"]}
    started = _submit(run_id)
    return {"run_id": run_id, "started": started, "status": "cloning" if started else "queued",
            **({} if started else {"detail": f"waiting for a free worker ({MAX_RUNS} runs at a time)"})}


@app.get("/runs/{run_id}/report.pdf")
def report_pdf(run_id: str, request: Request, x_aqp_token: Optional[str] = Header(default=None)) -> Response:
    """The run's Final Evaluation Report as a PDF (the web app checks the user's access before calling this)."""
    _check_token(x_aqp_token, request)
    row = store.load_run(run_id)
    report = (row or {}).get("finalReport")
    if isinstance(report, str):
        report = json.loads(report)
    html = (report or {}).get("html") if isinstance(report, dict) else None
    if not html:
        raise HTTPException(status_code=404, detail="this run has no final report")
    try:
        pdf = html_to_pdf(html)
    except Exception as exc:
        logger.warning(f"Report PDF for run {run_id} failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="The PDF could not be generated.")
    return Response(content=pdf, media_type="application/pdf")


@app.post("/runs/{run_id}/cancel", status_code=202)
def cancel_run(run_id: str, request: Request, x_aqp_token: Optional[str] = Header(default=None)) -> dict:
    """Ask a run to stop (the web app may also set Run.cancelRequested directly)."""
    _check_token(x_aqp_token, request)
    row = store.load_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    if row["status"] == "queued":
        store.update_run(run_id, status="cancelled", errorMessage="Cancelled by the user.")
    elif row["status"] not in ("completed", "failed", "cancelled"):
        store.update_run(run_id, cancelRequested=True)
    return {"run_id": run_id, "status": "cancelling"}
