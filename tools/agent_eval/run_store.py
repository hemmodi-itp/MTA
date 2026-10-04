"""
run_store.py — Postgres persistence for agent-evaluation runs.

Writes into the tables owned by the frontend's Prisma schema
(frontend/prisma/schema.prisma — that file is the source of truth; change the
schema there and add a Prisma migration (frontend/prisma/README.md), never DDL from Python).

Prisma conventions this module has to honour by hand:
  * table / column names are the model / field names, quoted ("Run"."currentStage")
  * ids are generated client-side (Prisma uses cuid) — we mint our own
  * DateTime columns are `timestamp(3)` without time zone, holding UTC
  * @updatedAt is set by the Prisma client, not the DB — we set it explicitly
"""

import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from connectors.db.postgres import PostgresConnector

# column → Postgres enum type, so string params get an explicit cast.
_ENUM_COLUMNS = {
    "Run": {"status": "RunStatus", "currentStage": "PipelineStage", "riskLevel": "RiskLevel", "mode": "SubmissionMode"},
    "Project": {"lastRunStatus": "RunStatus", "mode": "SubmissionMode"},
    "RunStep": {"key": "PipelineStage", "status": "StepStatus"},
    "RunEvent": {"stage": "PipelineStage"},
    "Requirement": {"status": "RequirementStatus"},
    "TestCase": {"status": "TestStatus"},
    "Recommendation": {"category": "RecommendationCategory", "severity": "Severity", "evidenceType": "EvidenceType"},
}
_JSON_COLUMNS = {"qualityBreakdown", "trend", "agentProfile", "acceptanceCriteria", "negativeSearch", "citation",
                 "scorecard", "gates", "runtimeProfile", "appClassification", "actionPlan",
                 "executionRun", "evidenceCollection", "outputValidation", "passFail", "brdCompliance",
                 "finalReport"}
_TERMINAL = ("completed", "failed", "cancelled")
RESTART_MARK = "Restarted after a service interruption"
_ACTIVE = ("cloning", "installing", "launching", "running")


def new_id() -> str:
    """cuid-shaped id: 'c' + 24 url-safe lowercase chars, time-ordered prefix."""
    return "c" + format(int(time.time() * 1000), "x")[-10:] + secrets.token_hex(7)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class RunStore:
    def __init__(self, db: Optional[PostgresConnector] = None) -> None:
        self.db = db or PostgresConnector()

    # ── generic helpers ─────────────────────────────────────────────────────

    def _placeholder(self, table: str, column: str) -> str:
        enum = _ENUM_COLUMNS.get(table, {}).get(column)
        return f"%s::{_q(enum)}" if enum else "%s"

    @staticmethod
    def _value(column: str, value: Any) -> Any:
        if column in _JSON_COLUMNS and value is not None:
            from psycopg.types.json import Jsonb
            return Jsonb(value)
        return value

    def _insert(self, conn, table: str, row: Dict[str, Any]) -> None:
        cols = list(row)
        sql = (f"INSERT INTO {_q(table)} ({', '.join(_q(c) for c in cols)}) "
               f"VALUES ({', '.join(self._placeholder(table, c) for c in cols)})")
        conn.execute(sql, [self._value(c, row[c]) for c in cols])

    def _update(self, conn, table: str, where: Dict[str, Any], fields: Dict[str, Any]) -> int:
        if not fields:
            return 0
        sets = ", ".join(f"{_q(c)} = {self._placeholder(table, c)}" for c in fields)
        conds = " AND ".join(f"{_q(c)} = {self._placeholder(table, c)}" for c in where)
        cur = conn.execute(
            f"UPDATE {_q(table)} SET {sets} WHERE {conds}",
            [self._value(c, v) for c, v in fields.items()] + [self._value(c, v) for c, v in where.items()],
        )
        return cur.rowcount

    # ── runs ────────────────────────────────────────────────────────────────

    def load_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            'SELECT r.*, p."name" AS "projectName", p."githubUrl", p."branch", '
            'p."mode" AS "projectMode", p."liveUrl" AS "projectLiveUrl", p."brdPath" AS "projectBrdPath", '
            'p."liveAuth" AS "projectLiveAuth" '
            'FROM "Run" r JOIN "Project" p ON p."id" = r."projectId" WHERE r."id" = %s',
            [run_id],
        )
        return rows[0] if rows else None

    def claim_run(self, run_id: str) -> bool:
        """Atomically move a queued run to 'cloning'. False if someone else has it."""
        with self.db.connection() as conn:
            cur = conn.execute(
                'UPDATE "Run" SET "status" = \'cloning\'::"RunStatus", "startedAt" = %s '
                'WHERE "id" = %s AND "status" = \'queued\'::"RunStatus"',
                [utcnow(), run_id],
            )
            return cur.rowcount == 1

    def update_run(self, run_id: str, **fields: Any) -> None:
        with self.db.connection() as conn:
            self._update(conn, "Run", {"id": run_id}, fields)

    def update_project(self, project_id: str, **fields: Any) -> None:
        fields.setdefault("updatedAt", utcnow())
        with self.db.connection() as conn:
            self._update(conn, "Project", {"id": project_id}, fields)

    def fail_orphaned_runs(self, reason: str, stale_after_s: int = 0, exclude: Iterable[str] = ()) -> List[str]:
        """Fail active runs no live worker owns: no heartbeat for `stale_after_s` seconds (0 = any active run, used at
        startup when this process owns nothing yet). Only those runs' running steps are failed. Returns their ids."""
        exclude = list(exclude)
        with self.db.connection() as conn:
            rows = conn.execute(
                'UPDATE "Run" SET "status" = \'failed\'::"RunStatus", "finishedAt" = %s, "errorMessage" = %s '
                'WHERE "status" IN (\'cloning\', \'installing\', \'launching\', \'running\') '
                'AND ("heartbeatAt" IS NULL OR "heartbeatAt" < %s) AND NOT ("id" = ANY(%s)) RETURNING "id", "projectId"',
                [utcnow(), reason, _ago(stale_after_s), exclude],
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                conn.execute(
                    'UPDATE "RunStep" SET "status" = \'failed\'::"StepStatus", "finishedAt" = %s, "detail" = %s '
                    'WHERE "status" = \'running\'::"StepStatus" AND "runId" = ANY(%s)',
                    [utcnow(), reason, ids],
                )
                conn.execute(
                    'UPDATE "Project" SET "lastRunStatus" = \'failed\'::"RunStatus", "updatedAt" = %s WHERE "id" = ANY(%s)',
                    [utcnow(), list({r["projectId"] for r in rows})],
                )
            return ids

    def requeue(self, run_ids: Iterable[str]) -> int:
        """Hand claimed-but-not-started runs back to the queue (graceful shutdown)."""
        ids = list(run_ids)
        if not ids:
            return 0
        with self.db.connection() as conn:
            cur = conn.execute(
                'UPDATE "Run" SET "status" = \'queued\'::"RunStatus" WHERE "id" = ANY(%s) '
                'AND "status" = \'cloning\'::"RunStatus" AND "currentStage" IS NULL',
                [ids],
            )
            return cur.rowcount

    def requeue_interrupted(self, run_id: str, note: str) -> bool:
        """Put a run that a service stop/restart interrupted back in the queue (once). False when it was already
        restarted after an interruption, so a run that keeps crashing the service cannot loop forever."""
        with self.db.connection() as conn:
            cur = conn.execute(
                'UPDATE "Run" SET "status" = \'queued\'::"RunStatus", "currentStage" = NULL, "heartbeatAt" = NULL, '
                '"errorMessage" = %s WHERE "id" = %s AND "status" NOT IN (\'completed\', \'failed\', \'cancelled\') '
                'AND COALESCE("errorMessage", \'\') NOT LIKE %s',
                [note, run_id, f"{RESTART_MARK}%"],
            )
            return cur.rowcount == 1

    def orphaned_run_ids(self, stale_after_s: int, exclude: Iterable[str] = ()) -> List[str]:
        rows = self.db.query(
            'SELECT "id" FROM "Run" WHERE "status" IN (\'cloning\', \'installing\', \'launching\', \'running\') '
            'AND ("heartbeatAt" IS NULL OR "heartbeatAt" < %s) AND NOT ("id" = ANY(%s))',
            [_ago(stale_after_s), list(exclude)])
        return [r["id"] for r in rows]

    def heartbeat(self, run_id: str) -> bool:
        """Mark the run alive; returns True when the user asked to cancel it."""
        rows = self.db.query('UPDATE "Run" SET "heartbeatAt" = %s WHERE "id" = %s RETURNING "cancelRequested"',
                             [utcnow(), run_id])
        return bool(rows and rows[0].get("cancelRequested"))

    def cancel_requested(self, run_id: str) -> bool:
        rows = self.db.query('SELECT "cancelRequested", "status" FROM "Run" WHERE "id" = %s', [run_id])
        return bool(rows and (rows[0].get("cancelRequested") or rows[0].get("status") == "cancelled"))

    def queued_run_ids(self) -> List[str]:
        rows = self.db.query('SELECT "id" FROM "Run" WHERE "status" = \'queued\'::"RunStatus" AND "mode" IS NOT NULL '
                             'ORDER BY "startedAt"')
        return [r["id"] for r in rows]

    # ── steps & events ──────────────────────────────────────────────────────

    def ensure_steps(self, run_id: str, steps: Iterable[Dict[str, str]]) -> None:
        with self.db.connection() as conn:
            for position, step in enumerate(steps):
                conn.execute(
                    'INSERT INTO "RunStep" ("id", "runId", "key", "label", "position", "status") '
                    'VALUES (%s, %s, %s::"PipelineStage", %s, %s, \'pending\'::"StepStatus") '
                    'ON CONFLICT ("runId", "key") DO UPDATE SET "label" = EXCLUDED."label", "position" = EXCLUDED."position", '
                    '"status" = \'pending\'::"StepStatus", "detail" = NULL, "startedAt" = NULL, "finishedAt" = NULL',
                    [new_id(), run_id, step["key"], step["label"], position],
                )

    def step(self, run_id: str, key: str, status: str, detail: Optional[str] = None) -> None:
        fields: Dict[str, Any] = {"status": status}
        if detail is not None:
            fields["detail"] = detail[:2000]
        if status == "running":
            fields["startedAt"] = utcnow()
        elif status in ("success", "failed", "skipped"):
            fields["finishedAt"] = utcnow()
        with self.db.connection() as conn:
            self._update(conn, "RunStep", {"runId": run_id, "key": key}, fields)

    def step_detail(self, run_id: str, key: str, detail: str) -> None:
        """Live progress text for a running step (timestamps untouched)."""
        with self.db.connection() as conn:
            self._update(conn, "RunStep", {"runId": run_id, "key": key}, {"detail": detail[:2000]})

    def event(self, run_id: str, message: str, level: str = "info", stage: Optional[str] = None) -> None:
        with self.db.connection() as conn:
            self._insert(conn, "RunEvent", {
                "id": new_id(), "runId": run_id, "createdAt": utcnow(), "level": level,
                "stage": stage, "message": message[:4000],
            })

    # ── requirements ────────────────────────────────────────────────────────

    def replace_requirements(self, run_id: str, requirements: List[Dict[str, Any]]) -> None:
        """Insert requirements and their acceptance criteria; mutates each dict/criterion with its DB id."""
        with self.db.connection() as conn:
            conn.execute('DELETE FROM "Requirement" WHERE "runId" = %s', [run_id])  # criteria cascade
            for r in requirements:
                r["id"] = new_id()
                self._insert(conn, "Requirement", {
                    "id": r["id"], "runId": run_id, "code": r["code"], "title": r["title"][:500],
                    "description": r.get("description") or "", "priority": r.get("priority") or "medium",
                    "kind": r.get("kind") or "functional",
                    "acceptanceCriteria": r.get("acceptance_criteria") or [],
                    "section": r.get("section"), "sourceQuote": r.get("source_quote"),
                    "status": r.get("status") or "unknown", "evidence": r.get("evidence"),
                    "verifiability": r.get("verifiability") or "both", "origin": r.get("origin") or "brd",
                    "confidence": float(r.get("confidence", 1.0)),
                })
                for c in r.get("criteria") or []:
                    c["id"] = new_id()
                    self._insert(conn, "AcceptanceCriterion", {
                        "id": c["id"], "runId": run_id, "requirementId": r["id"], "code": c["code"],
                        "statement": c["statement"], "oracleHint": c.get("oracle_hint") or "semantic",
                        "weight": float(c.get("weight", 1.0)),
                    })

    def save_criterion_verdict(self, criterion_id: str, v: Dict[str, Any]) -> None:
        with self.db.connection() as conn:
            self._update(conn, "AcceptanceCriterion", {"id": criterion_id}, {
                "verdict": v["verdict"], "bestStrength": v.get("best_strength"), "credit": v.get("credit"),
                "agreement": v.get("agreement"), "rationale": (v.get("rationale") or "")[:4000] or None,
                "negativeSearch": v.get("negative_search"),
            })

    def save_criterion_verdicts(self, verdicts: List[Dict[str, Any]]) -> None:
        """All criterion verdicts of a run in one transaction (one row update each)."""
        rows = [v for v in verdicts if v.get("criterion_id")]
        if not rows:
            return
        with self.db.connection() as conn:
            for v in rows:
                self._update(conn, "AcceptanceCriterion", {"id": v["criterion_id"]}, {
                    "verdict": v["verdict"], "bestStrength": v.get("best_strength"), "credit": v.get("credit"),
                    "agreement": v.get("agreement"), "rationale": (v.get("rationale") or "")[:4000] or None,
                    "negativeSearch": v.get("negative_search"),
                })

    def save_requirement_verdicts(self, requirements: List[Dict[str, Any]]) -> None:
        rows = [r for r in requirements if r.get("id") and r.get("verdict")]
        if not rows:
            return
        with self.db.connection() as conn:
            for r in rows:
                self._update(conn, "Requirement", {"id": r["id"]}, {
                    "verdict": r["verdict"], "score": r.get("score") or 0.0, "status": r.get("status") or "unknown"})

    def replace_evidence(self, run_id: str, items: List[Dict[str, Any]]) -> None:
        """Replace the run's evidence rows (static trace first, then the merged static + runtime set)."""
        with self.db.connection() as conn:
            conn.execute('DELETE FROM "Evidence" WHERE "runId" = %s', [run_id])
        self.add_evidence(run_id, items)

    def save_requirement_verdict(self, requirement_id: str, verdict: str, score: float, legacy_status: str) -> None:
        with self.db.connection() as conn:
            self._update(conn, "Requirement", {"id": requirement_id},
                         {"verdict": verdict, "score": score, "status": legacy_status})

    def add_evidence(self, run_id: str, items: List[Dict[str, Any]]) -> None:
        if not items:
            return
        with self.db.connection() as conn:
            for e in items:
                self._insert(conn, "Evidence", {
                    "id": new_id(), "runId": run_id, "criterionId": e.get("criterion_id"), "method": e["method"],
                    "strength": e["strength"], "outcome": e["outcome"], "citation": e.get("citation"),
                    "testCaseId": e.get("test_case_id"), "summary": (e.get("summary") or "")[:4000],
                    "validated": bool(e.get("validated")), "createdAt": utcnow(),
                })

    def replace_findings(self, run_id: str, findings: List[Dict[str, Any]]) -> None:
        with self.db.connection() as conn:
            conn.execute('DELETE FROM "Finding" WHERE "runId" = %s', [run_id])
            for f in findings:
                self._insert(conn, "Finding", {
                    "id": new_id(), "runId": run_id, "dimension": f["dimension"], "ruleId": f.get("rule_id"),
                    "severity": f["severity"], "title": f["title"][:500], "filePath": f.get("file"),
                    "startLine": f.get("start_line"), "endLine": f.get("end_line"),
                    "rationale": f.get("rationale"), "fix": f.get("fix"), "source": f.get("source") or "scanner",
                    "confidence": float(f.get("confidence", 1.0)),
                })

    def update_requirement(self, run_id: str, code: str, status: str, evidence: Optional[str]) -> None:
        with self.db.connection() as conn:
            self._update(conn, "Requirement", {"runId": run_id, "code": code},
                         {"status": status, "evidence": (evidence or "")[:4000] or None})

    # ── test cases ──────────────────────────────────────────────────────────

    def replace_test_cases(self, run_id: str, tests: List[Dict[str, Any]]) -> None:
        """Insert generated tests; mutates each dict to carry its DB id under 'id'."""
        with self.db.connection() as conn:
            conn.execute('DELETE FROM "TestCase" WHERE "runId" = %s', [run_id])
            for t in tests:
                t["id"] = t.get("id") or new_id()
                self._insert(conn, "TestCase", {
                    "id": t["id"], "runId": run_id,
                    "scenarioTitle": f"{t['code']} · {t['title']}"[:500],
                    "module": t.get("area") or ("General" if t.get("category") == "general" else "Agent"),
                    "variantType": t.get("variant_type") or "positive",
                    "status": t.get("status") or "pending",
                    "durationMs": 0, "healed": False,
                    "category": t.get("category"), "requirementRef": t.get("requirement_ref"),
                    "priority": t.get("priority"), "input": t.get("input"),
                    "expected": t.get("expected_behavior"),
                    "brdReference": t.get("brd_reference"), "acceptanceCriterion": t.get("acceptance_criterion"),
                    "criterionCode": t.get("criterion_code"),
                    "specPreview": _spec_preview(t),
                })

    def finalize_pending_tests(self, run_id: str, reason: str) -> int:
        """When a run ends, no test may stay 'pending': give the ones nobody ran an explicit reason."""
        with self.db.connection() as conn:
            cur = conn.execute(
                'UPDATE "TestCase" SET "status" = \'not_executed\'::"TestStatus", "errorSummary" = %s '
                'WHERE "runId" = %s AND "status" = \'pending\'::"TestStatus"',
                [f"Not executed: {reason}"[:1000], run_id],
            )
            return cur.rowcount

    def update_test_case(self, test_id: str, **fields: Any) -> None:
        with self.db.connection() as conn:
            self._update(conn, "TestCase", {"id": test_id}, fields)

    # ── recommendations ─────────────────────────────────────────────────────

    def replace_recommendations(self, run_id: str, recs: List[Dict[str, Any]]) -> None:
        with self.db.connection() as conn:
            conn.execute('DELETE FROM "Recommendation" WHERE "runId" = %s', [run_id])
            for r in recs:
                self._insert(conn, "Recommendation", {
                    "id": new_id(), "runId": run_id, "category": r["category"], "severity": r["severity"],
                    "summary": r["summary"][:2000], "evidenceRef": r.get("evidence_ref") or "",
                    "evidenceType": r.get("evidence_type") or "scenario",
                })

    def recent_scores(self, project_id: str, limit: int = 9) -> List[int]:
        rows = self.db.query(
            'SELECT "qualityScore" FROM "Run" WHERE "projectId" = %s AND "status" = \'completed\'::"RunStatus" '
            'AND "complianceScore" IS NOT NULL ORDER BY "finishedAt" DESC NULLS LAST LIMIT %s',
            [project_id, limit],
        )
        return [int(r["qualityScore"]) for r in reversed(rows)]


def _ago(seconds: int):
    from datetime import timedelta
    return utcnow() - timedelta(seconds=max(0, int(seconds)))


def _spec_preview(t: Dict[str, Any]) -> str:
    lines = [f"# {t['code']} — {t['title']}", f"Category: {t.get('category')} · Type: {t.get('variant_type')} · Priority: {t.get('priority')}"]
    if t.get("requirement_ref"):
        lines.append(f"Requirement: {t['requirement_ref']}")
    if t.get("brd_reference"):
        lines += ["", "## BRD reference", f"> {t['brd_reference']}"]
    if t.get("acceptance_criterion"):
        lines += ["", "## Acceptance criterion", str(t["acceptance_criterion"])]
    lines += ["", "## Input", str(t.get("input") or ""), "", "## Expected behaviour", str(t.get("expected_behavior") or "")]
    criteria = t.get("pass_criteria") or []
    if criteria:
        lines += ["", "## Pass criteria"] + [f"- {c}" for c in criteria]
    return "\n".join(lines)
